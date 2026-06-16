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
    "corpus": "academic",
    "synthesis": "academic",
    "scrape": "strategic",
    "api": "strategic",
    "market": "strategic",
    "financial": "strategic",
}


def _finding_text(entry: Any, *keys: str) -> str:
    """Safely extract display text from a list entry.

    Entries from tool responses may be strings, dicts (preferred keys tried
    in order), or other scalars (ints, floats, bools). This never raises on
    non-dict, non-str input - e.g. an ``insights: [5, 7]`` list - which a bare
    ``entry.get(...)`` would crash on.
    """
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        for key in keys:
            value = entry.get(key)
            if value:
                return str(value)
    return str(entry)


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

    def categorize_recon_response(self, payload: dict[str, Any], domain: str = "") -> list[AbsorbedFinding]:
        """Specialized high-fidelity parser for real recon-tool lookup_tenant (and kin) output.

        Understands the concrete shape shipped by recon-tool:
        - services (list of slugs or objects)
        - related_domains / tenant_domains
        - insights (list of strings or objects)
        - top-level tenant / provider / email_security info

        Always emits "infrastructure" findings at >=0.8 confidence (cost:0 instrument).
        Falls back gracefully to generic extraction.
        """
        findings: list[AbsorbedFinding] = []
        if not isinstance(payload, dict):
            return findings

        # MCPClientProxy wraps result under 'result' for some paths; unwrap
        raw = payload.get("result", payload) if "result" in payload else payload
        if not isinstance(raw, dict):
            return findings
        data: dict[str, Any] = raw

        # Primary: services (highest signal)
        services = data.get("services") or []
        if isinstance(services, list):
            for svc in services:
                if not svc:
                    continue
                text = _finding_text(svc, "name", "slug")
                findings.append(
                    AbsorbedFinding(
                        text=f"Detected service: {text}",
                        category="infrastructure",
                        confidence=0.88,
                        source_type="DNS",
                        source_tool="recon/lookup_tenant",
                        raw_data={"domain": domain, "service": svc},
                    )
                )

        # Related domains (strong infrastructure signal)
        for key in ("related_domains", "tenant_domains", "aliases"):
            rel = data.get(key) or []
            if isinstance(rel, list):
                for r in rel[:10]:  # cap noise
                    if r:
                        text = r if isinstance(r, str) else str(r)
                        findings.append(
                            AbsorbedFinding(
                                text=f"Related domain: {text}",
                                category="infrastructure",
                                confidence=0.82,
                                source_type="DNS",
                                source_tool="recon/lookup_tenant",
                                raw_data={"domain": domain, "related": r},
                            )
                        )

        # Insights (derived observations — still high value for infrastructure)
        insights = data.get("insights") or []
        if isinstance(insights, list):
            for ins in insights[:8]:
                if not ins:
                    continue
                text = _finding_text(ins, "text")
                findings.append(
                    AbsorbedFinding(
                        text=f"Insight: {text}",
                        category="infrastructure",
                        confidence=0.80,
                        source_type="DNS",
                        source_tool="recon/lookup_tenant",
                        raw_data={"domain": domain, "insight": ins},
                    )
                )

        # Top-level tenant / provider / email security posture (very high signal)
        tenant = data.get("tenant") or data.get("company") or data.get("name")
        provider = data.get("provider") or data.get("primary_provider")
        if tenant or provider:
            parts = []
            if tenant:
                parts.append(f"tenant={tenant}")
            if provider:
                parts.append(f"provider={provider}")
            findings.append(
                AbsorbedFinding(
                    text="Identity: " + ", ".join(parts),
                    category="infrastructure",
                    confidence=0.90,
                    source_type="DNS",
                    source_tool="recon/lookup_tenant",
                    raw_data={"domain": domain, "tenant": tenant, "provider": provider},
                )
            )

        # Email security posture block if present
        email_sec = data.get("email_security") or data.get("dmarc") or data.get("spf")
        if email_sec:
            findings.append(
                AbsorbedFinding(
                    text=f"Email security posture: {email_sec if isinstance(email_sec, str) else 'present'}",
                    category="infrastructure",
                    confidence=0.85,
                    source_type="DNS",
                    source_tool="recon/lookup_tenant",
                    raw_data={"domain": domain, "email_security": email_sec},
                )
            )

        # Final fallback: if we still have nothing but real data, make one synthetic finding
        if not findings and data:
            summary = data.get("summary") or str(list(data.keys())[:6])
            findings.append(
                AbsorbedFinding(
                    text=f"Recon data for {domain or 'domain'}: {summary}"[:220],
                    category="infrastructure",
                    confidence=0.78,
                    source_type="DNS",
                    source_tool="recon/lookup_tenant",
                    raw_data=data,
                )
            )

        return findings

    def categorize_distillr_response(
        self,
        payload: dict[str, Any],
        topic: str = "",
        tool: str = "distillr/papers",
    ) -> list[AbsorbedFinding]:
        """Specialized parser for distillr corpus-ingestion / query output.

        Understands the concrete shape shipped by the distillr MCP server:
        - topic, papers_ingested / videos_ingested / sites_ingested counts
        - synthesis_path / corpus_synthesis_path (the high-value artifacts)
        - insights / key_findings / results (per-source or query hits)
        - cost (actual spend, surfaced for provenance, not absorbed as a belief)

        Distillr produces synthesized source material, so findings are emitted
        as "academic" knowledge with citations to the corpus artifact for
        provenance. Confidence is moderate (multi-source synthesis, not
        primary fact) and tops out below recon's DNS-grade certainty.

        Falls back gracefully to a single summary finding for unrecognised
        shapes (e.g. find_insights metadata-only responses).
        """
        findings: list[AbsorbedFinding] = []
        if not isinstance(payload, dict):
            return findings

        # MCPClientProxy wraps result under 'result' for some paths; unwrap.
        raw = payload.get("result", payload) if "result" in payload else payload
        if not isinstance(raw, dict):
            return findings
        data: dict[str, Any] = raw
        topic = topic or str(data.get("topic") or data.get("query") or "").strip()

        # Highest-value artifact: the synthesis over the ingested corpus.
        synthesis = data.get("corpus_synthesis_path") or data.get("synthesis_path")
        counts = {
            "papers": data.get("papers_ingested"),
            "videos": data.get("videos_ingested"),
            "sites": data.get("sites_ingested"),
            "sources": data.get("items_ingested") or data.get("count"),
        }
        ingested = [(k, int(v)) for k, v in counts.items() if isinstance(v, (int, float)) and v]
        if synthesis or ingested:
            summary = ", ".join(f"{n} {kind}" for kind, n in ingested) or "sources"
            label = f" on '{topic}'" if topic else ""
            text = f"Ingested corpus ({summary}){label}"
            if synthesis:
                text += f"; synthesis at {synthesis}"
            findings.append(
                AbsorbedFinding(
                    text=text,
                    category="academic",
                    confidence=0.75,
                    source_type="corpus",
                    source_tool=tool,
                    raw_data={"topic": topic, "synthesis": synthesis, "counts": dict(ingested)},
                )
            )

        # Insights / key findings / query results (per-source signal). Consume
        # the first NON-EMPTY list-shaped key only, to avoid double counting
        # the same material reported under several keys.
        for key in ("insights", "key_findings", "findings", "results", "items"):
            entries = data.get(key)
            if not isinstance(entries, list) or not entries:
                continue
            for entry in entries[:10]:  # cap noise
                if not entry:
                    continue
                text = _finding_text(entry, "text", "title")
                findings.append(
                    AbsorbedFinding(
                        text=str(text)[:300],
                        category="academic",
                        confidence=0.72,
                        source_type="paper",
                        source_tool=tool,
                        raw_data={"topic": topic, "entry": entry},
                    )
                )
            break

        # Fallback: real data but no recognised structure (e.g. query metadata).
        if not findings and data:
            summary = data.get("summary") or str(list(data.keys())[:6])
            findings.append(
                AbsorbedFinding(
                    text=f"Distillr corpus for {topic or 'topic'}: {summary}"[:220],
                    category="academic",
                    confidence=0.70,
                    source_type="corpus",
                    source_tool=tool,
                    raw_data=data,
                )
            )

        return findings

    def categorize_primr_response(
        self,
        payload: dict[str, Any],
        company: str = "",
        tool: str = "primr/research_company",
    ) -> list[AbsorbedFinding]:
        """Specialized parser for primr strategic company-intelligence output.

        Unlike recon (all infrastructure) and distillr (all academic), primr
        is genuinely multi-category: it folds a recon pre-flight (infrastructure
        facts) into AI-synthesized strategic analysis (positioning, hiring
        signals, initiatives). This parser emits findings across BOTH
        categories with category-appropriate confidence:
        - recon_summary -> infrastructure (factual, higher confidence)
        - hiring_signals / initiatives / positioning -> strategic (synthesized)

        The report/strategy artifact paths are carried as provenance. Cost and
        duration are surfaced in raw_data, not absorbed as beliefs.

        Falls back to a single strategic summary finding for unrecognised
        shapes (e.g. estimate_run / check_jobs metadata).
        """
        findings: list[AbsorbedFinding] = []
        if not isinstance(payload, dict):
            return findings

        raw = payload.get("result", payload) if "result" in payload else payload
        if not isinstance(raw, dict):
            return findings
        data: dict[str, Any] = raw
        company = company or str(data.get("company") or data.get("domain") or "").strip()

        # Headline: the strategic brief itself, citing its artifact for provenance.
        report = data.get("report_path") or data.get("strategy_path")
        if report or data.get("sections") or data.get("mode"):
            label = f" for {company}" if company else ""
            findings.append(
                AbsorbedFinding(
                    text=f"Strategic brief{label} ({data.get('sections') or '?'} sections, "
                    f"{data.get('citations') or '?'} citations)" + (f"; report at {report}" if report else ""),
                    category="strategic",
                    confidence=0.72,
                    source_type="scrape",
                    source_tool=tool,
                    raw_data={
                        "company": company,
                        "report_path": data.get("report_path"),
                        "strategy_path": data.get("strategy_path"),
                        "cost": data.get("cost"),
                        "duration_minutes": data.get("duration_minutes"),
                    },
                )
            )

        # Infrastructure facts from the embedded recon pre-flight.
        recon_summary = data.get("recon_summary")
        if isinstance(recon_summary, dict) and recon_summary:
            provider = recon_summary.get("provider")
            svc_count = recon_summary.get("services_count")
            parts = []
            if provider:
                parts.append(f"provider={provider}")
            if svc_count is not None:
                parts.append(f"services={svc_count}")
            findings.append(
                AbsorbedFinding(
                    text=f"Infrastructure (recon pre-flight){f' for {company}' if company else ''}: "
                    + (", ".join(parts) or "present"),
                    category="infrastructure",
                    confidence=0.82,
                    source_type="DNS",
                    source_tool=tool,
                    raw_data={"company": company, "recon_summary": recon_summary},
                )
            )

        # Hiring signals -> strategic.
        hiring = data.get("hiring_signals")
        if isinstance(hiring, dict) and hiring:
            total = hiring.get("total_roles")
            ml = hiring.get("ml_roles")
            inits = hiring.get("top_initiatives") or []
            roles = total if total is not None else "?"
            text = f"Hiring signals{f' for {company}' if company else ''}: {roles} roles"
            if ml is not None:
                text += f", {ml} ML"
            if isinstance(inits, list) and inits:
                text += "; initiatives: " + ", ".join(str(i) for i in inits[:5])
            findings.append(
                AbsorbedFinding(
                    text=text,
                    category="strategic",
                    confidence=0.70,
                    source_type="scrape",
                    source_tool=tool,
                    raw_data={"company": company, "hiring_signals": hiring},
                )
            )

        # Strategic initiatives / key findings -> strategic (first non-empty list).
        for key in ("strategic_initiatives", "initiatives", "key_findings", "insights", "findings"):
            entries = data.get(key)
            if not isinstance(entries, list) or not entries:
                continue
            for entry in entries[:10]:
                if not entry:
                    continue
                text = _finding_text(entry, "text", "title")
                findings.append(
                    AbsorbedFinding(
                        text=str(text)[:300],
                        category="strategic",
                        confidence=0.68,
                        source_type="scrape",
                        source_tool=tool,
                        raw_data={"company": company, "entry": entry},
                    )
                )
            break

        # Fallback: real data but no recognised structure (estimate/job metadata).
        if not findings and data:
            summary = data.get("summary") or str(list(data.keys())[:6])
            findings.append(
                AbsorbedFinding(
                    text=f"Primr data for {company or 'company'}: {summary}"[:220],
                    category="strategic",
                    confidence=0.60,
                    source_type="scrape",
                    source_tool=tool,
                    raw_data=data,
                )
            )

        return findings
