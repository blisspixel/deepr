"""Knowledge absorption from external tool outputs.

Parses structured tool responses into categorized findings with
confidence levels for integration into expert belief states.

Feature: mcp-client-agent-interop
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Confidence thresholds by category
_CONFIDENCE_THRESHOLDS: dict[str, float] = {
    "infrastructure": 0.8,
    "academic": 0.7,
    "strategic": 0.5,
}

# Source type to category mapping
_SOURCE_CATEGORY_MAP: dict[str, str] = {
    "DNS": "infrastructure",
    "dns": "infrastructure",
    "whois": "infrastructure",
    "network": "infrastructure",
    "paper": "academic",
    "citation": "academic",
    "journal": "academic",
    "scrape": "strategic",
    "api": "strategic",
    "market": "strategic",
    "financial": "strategic",
}


@dataclass
class AbsorbedFinding:
    """A single finding extracted from external tool output."""

    text: str
    category: str  # "infrastructure" | "academic" | "strategic"
    confidence: float  # 0.0 - 1.0
    source_type: str  # e.g., "DNS", "paper", "scrape", "api"
    source_tool: str  # e.g., "recon/domain_lookup"
    raw_data: dict[str, Any] = field(default_factory=dict)


class KnowledgeAbsorber:
    """Parse external tool output into categorized findings.

    Classifies findings by category (infrastructure, academic, strategic)
    and assigns confidence levels based on source type.

    Usage::

        absorber = KnowledgeAbsorber()
        findings = absorber.absorb(tool_response, source_type="DNS")
        for f in findings:
            print(f"{f.category}: {f.text} (confidence={f.confidence})")
    """

    def categorize(self, data: dict[str, Any]) -> str:
        """Classify findings based on data content.

        Looks at source_type field or infers from data keys.

        Returns:
            One of: "infrastructure", "academic", "strategic"
        """
        source_type = data.get("source_type", "")
        if source_type:
            category = _SOURCE_CATEGORY_MAP.get(source_type, "strategic")
            return category

        # Infer from data keys
        keys = set(data.keys())
        infra_keys = {"provider", "dns", "ip", "nameservers", "mx", "services"}
        academic_keys = {"title", "authors", "abstract", "doi", "citations"}

        if keys & infra_keys:
            return "infrastructure"
        if keys & academic_keys:
            return "academic"
        return "strategic"

    def absorb(
        self,
        tool_response: dict[str, Any],
        source_type: str,
        source_tool: str = "",
    ) -> list[AbsorbedFinding]:
        """Parse structured tool response into findings with confidence.

        Confidence assignment:
        - DNS/infrastructure → 0.8+
        - academic → 0.7+
        - strategic → 0.5+

        Args:
            tool_response: Structured response from external tool.
            source_type: Type of source (DNS, paper, scrape, api).
            source_tool: Tool identifier (e.g., "recon/domain_lookup").

        Returns:
            List of AbsorbedFinding with category and confidence.
        """
        findings: list[AbsorbedFinding] = []
        category = _SOURCE_CATEGORY_MAP.get(source_type, "strategic")
        base_confidence = _CONFIDENCE_THRESHOLDS.get(category, 0.5)

        # Extract findings from response structure
        items = self._extract_items(tool_response)

        for item in items:
            text = item.get("text", "") or item.get("value", "") or str(item)
            confidence = self._compute_confidence(item, base_confidence)

            findings.append(
                AbsorbedFinding(
                    text=str(text),
                    category=category,
                    confidence=confidence,
                    source_type=source_type,
                    source_tool=source_tool,
                    raw_data=item if isinstance(item, dict) else {"value": item},
                )
            )

        # If no items extracted, create a single finding from the response
        if not findings and tool_response:
            text = tool_response.get("summary", "") or str(tool_response)
            findings.append(
                AbsorbedFinding(
                    text=str(text)[:200],
                    category=category,
                    confidence=base_confidence,
                    source_type=source_type,
                    source_tool=source_tool,
                    raw_data=tool_response,
                )
            )

        return findings

    def _extract_items(self, response: dict[str, Any]) -> list[Any]:
        """Extract individual items from a tool response."""
        # Try common response structures
        for key in ("results", "findings", "items", "records", "data"):
            if key in response and isinstance(response[key], list):
                return response[key]

        # For DNS/recon responses
        for key in ("services", "related_domains", "insights"):
            if key in response and isinstance(response[key], list):
                return response[key]

        return []

    def _compute_confidence(
        self,
        item: Any,
        base_confidence: float,
    ) -> float:
        """Compute confidence for a single finding.

        Adjusts base confidence based on item quality signals.
        """
        if not isinstance(item, dict):
            return base_confidence

        # Boost for items with explicit confidence
        if "confidence" in item:
            try:
                return max(base_confidence, min(1.0, float(item["confidence"])))
            except (TypeError, ValueError):
                pass

        # Slight boost for items with more data
        field_count = len(item)
        if field_count >= 5:
            return min(1.0, base_confidence + 0.05)

        return base_confidence
