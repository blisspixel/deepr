"""Evidence schema v1 - Canonical citation format.

This module defines the canonical evidence schema used across:
- CLI output
- MCP payloads
- Saved reports

All interfaces MUST use this schema for citations to ensure consistency.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
import hashlib
import json


class Verdict(Enum):
    """Fact verification verdict with clear semantics."""
    TRUE = "TRUE"        # Claim supported by evidence within scope
    FALSE = "FALSE"      # Claim contradicted by evidence within scope
    UNCERTAIN = "UNCERTAIN"  # Insufficient or conflicting evidence


@dataclass
class Evidence:
    """Canonical evidence object with stable ID and provenance.
    
    Used across CLI output, MCP payloads, and saved reports.
    The evidence[] array is the canonical citation data; inline markers
    are a presentation view derived from evidence[] and SHALL NOT diverge.
    
    Attributes:
        id: Content-hash based ID, stable across runs
        source: Filename or document title
        url: URL if available
        quote: Exact quoted text from source
        span: Character span in source (start, end)
        retrieved_at: When this evidence was retrieved
        supports: List of claim IDs this evidence supports
        contradicts: List of claim IDs this evidence contradicts
    """
    id: str
    source: str
    url: Optional[str] = None
    quote: str = ""
    span: Optional[tuple] = None
    retrieved_at: datetime = field(default_factory=datetime.utcnow)
    supports: List[str] = field(default_factory=list)
    contradicts: List[str] = field(default_factory=list)
    
    @classmethod
    def create(cls, source: str, quote: str, **kwargs) -> "Evidence":
        """Create evidence with content-hash ID.
        
        The ID is derived from source + quote content, ensuring
        the same evidence always gets the same ID.
        """
        content = f"{source}:{quote}"
        id_hash = hashlib.sha256(content.encode()).hexdigest()[:12]
        return cls(id=id_hash, source=source, quote=quote, **kwargs)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "source": self.source,
            "url": self.url,
            "quote": self.quote,
            "span": list(self.span) if self.span else None,
            "retrieved_at": self.retrieved_at.isoformat(),
            "supports": self.supports,
            "contradicts": self.contradicts
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Evidence":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            source=data["source"],
            url=data.get("url"),
            quote=data.get("quote", ""),
            span=tuple(data["span"]) if data.get("span") else None,
            retrieved_at=datetime.fromisoformat(data["retrieved_at"]) if data.get("retrieved_at") else datetime.utcnow(),
            supports=data.get("supports", []),
            contradicts=data.get("contradicts", [])
        )
    
    def to_inline_citation(self) -> str:
        """Generate inline citation marker.
        
        Format: [Source: filename.md]
        """
        return f"[Source: {self.source}]"
    
    def to_footnote(self) -> str:
        """Generate footnote with URL if available."""
        if self.url:
            return f"[{self.id}]: {self.source} - {self.url}"
        return f"[{self.id}]: {self.source}"


@dataclass
class FactCheckResult:
    """Structured result from fact verification.
    
    Used by `deepr check` command and MCP fact verification tools.
    """
    claim: str
    verdict: Verdict
    confidence: float  # 0.0-1.0, calibrated
    scope: str         # What sources/domain was checked
    evidence: List[Evidence] = field(default_factory=list)
    reasoning: str = ""  # Brief explanation
    cost: float = 0.0    # Cost of verification
    
    def to_cli_output(self) -> str:
        """Render for CLI display."""
        verdict_color = {
            Verdict.TRUE: "green",
            Verdict.FALSE: "red", 
            Verdict.UNCERTAIN: "yellow"
        }[self.verdict]
        
        lines = [
            f"[{verdict_color}]{self.verdict.value}[/{verdict_color}] (confidence: {self.confidence:.0%})",
            f"Scope: {self.scope}",
        ]
        
        if self.reasoning:
            lines.append(f"Reasoning: {self.reasoning}")
        
        if self.evidence:
            lines.append("")
            lines.append("Evidence:")
            for e in self.evidence:
                # Show support/contradict indicator
                if self.claim in str(e.supports):
                    marker = "[green]+[/green]"
                elif self.claim in str(e.contradicts):
                    marker = "[red]-[/red]"
                else:
                    marker = "[dim]?[/dim]"
                
                quote_preview = e.quote[:100] + "..." if len(e.quote) > 100 else e.quote
                lines.append(f"  {marker} {e.source}: \"{quote_preview}\"")
                if e.url:
                    lines.append(f"      [dim]{e.url}[/dim]")
        
        if self.cost > 0:
            lines.append(f"\n[dim]Cost: ${self.cost:.4f}[/dim]")
        
        return "\n".join(lines)
    
    def to_mcp_payload(self) -> Dict[str, Any]:
        """Render for MCP tool response."""
        return {
            "claim": self.claim,
            "verdict": self.verdict.value,
            "confidence": self.confidence,
            "scope": self.scope,
            "evidence": [e.to_dict() for e in self.evidence],
            "reasoning": self.reasoning,
            "cost": self.cost
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return self.to_mcp_payload()
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FactCheckResult":
        """Create from dictionary."""
        return cls(
            claim=data["claim"],
            verdict=Verdict(data["verdict"]),
            confidence=data["confidence"],
            scope=data["scope"],
            evidence=[Evidence.from_dict(e) for e in data.get("evidence", [])],
            reasoning=data.get("reasoning", ""),
            cost=data.get("cost", 0.0)
        )


@dataclass 
class ExpertAnswer:
    """Structured answer from expert query.
    
    Canonical format for expert responses across CLI and MCP.
    """
    answer_text: str
    evidence: List[Evidence] = field(default_factory=list)
    confidence: float = 0.0
    cost: float = 0.0
    reasoning_trace: Optional[str] = None  # For --verbose mode
    
    def to_cli_output(self, verbose: bool = False) -> str:
        """Render for CLI display."""
        lines = [self.answer_text]
        
        if self.evidence:
            lines.append("")
            lines.append("[dim]Sources:[/dim]")
            for e in self.evidence:
                lines.append(f"  - {e.source}")
                if e.url:
                    lines.append(f"    {e.url}")
        
        if verbose and self.reasoning_trace:
            lines.append("")
            lines.append("[dim]Reasoning:[/dim]")
            lines.append(self.reasoning_trace)
        
        if self.cost > 0:
            lines.append(f"\n[dim]Cost: ${self.cost:.4f}[/dim]")
        
        return "\n".join(lines)
    
    def to_mcp_payload(self) -> Dict[str, Any]:
        """Render for MCP tool response."""
        return {
            "answer": self.answer_text,
            "evidence": [e.to_dict() for e in self.evidence],
            "confidence": self.confidence,
            "cost": self.cost
        }
