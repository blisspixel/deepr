"""
Research result formatting with citation preservation.

This module transforms raw research results into formatted markdown
following the standard report template while preserving all citations.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
import re


@dataclass
class Citation:
    """A single citation reference."""
    index: int
    source: str
    url: Optional[str] = None
    accessed: Optional[str] = None
    
    def format(self) -> str:
        """Format citation for bibliography."""
        parts = [f"[{self.index}]", self.source]
        if self.url:
            parts.append(self.url)
        if self.accessed:
            parts.append(f"Accessed {self.accessed}.")
        return " ".join(parts)


@dataclass
class ResearchMetadata:
    """Metadata about the research operation."""
    mode: str
    model: str
    duration_seconds: int
    cost: float
    job_id: str
    timestamp: Optional[datetime] = None
    
    @property
    def duration_formatted(self) -> str:
        if self.duration_seconds < 60:
            return f"{self.duration_seconds} seconds"
        minutes = self.duration_seconds // 60
        seconds = self.duration_seconds % 60
        if seconds == 0:
            return f"{minutes} minutes"
        return f"{minutes}m {seconds}s"
    
    @property
    def cost_formatted(self) -> str:
        if self.cost == 0:
            return "FREE"
        return f"${self.cost:.4f}"
    
    @property
    def timestamp_formatted(self) -> str:
        ts = self.timestamp or datetime.now()
        return ts.isoformat()


@dataclass
class RawResult:
    """Raw research result before formatting."""
    title: str
    summary: str
    findings: list[str]
    analysis: str
    recommendations: list[str]
    citations: list[Citation]
    metadata: ResearchMetadata


def extract_citations(text: str) -> tuple[str, list[Citation]]:
    """
    Extract inline citations from text and return normalized text with citation list.
    
    Supports formats:
    - [1], [2], etc. (numeric references)
    - [Source Name](url) (markdown links used as citations)
    - (Source, Year) (academic style - not currently extracted)
    
    Args:
        text: Text to process (can be empty or None)
    
    Returns:
        Tuple of (text with normalized citations, list of Citation objects)
        Returns (empty string, empty list) for None/empty input
    
    Note:
        Markdown links are converted to numeric citations [N] and added
        to the citation list with URL preserved.
    """
    # Handle None or empty text
    if not text:
        return "", []
    
    citations: list[Citation] = []
    citation_map: dict[str, int] = {}
    
    # Pattern for markdown links used as citations
    link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
    
    def replace_link(match: re.Match) -> str:
        source = match.group(1)
        url = match.group(2)
        key = f"{source}|{url}"
        
        if key not in citation_map:
            idx = len(citations) + 1
            citation_map[key] = idx
            citations.append(Citation(
                index=idx,
                source=source,
                url=url,
                accessed=datetime.now().strftime("%Y-%m-%d"),
            ))
        
        return f"[{citation_map[key]}]"
    
    normalized = re.sub(link_pattern, replace_link, text)
    
    # Pattern for existing numeric citations [N]
    existing_pattern = r'\[(\d+)\]'
    existing_refs = set(int(m.group(1)) for m in re.finditer(existing_pattern, normalized))
    
    # Add placeholder citations for numeric refs not yet in list
    for ref_num in sorted(existing_refs):
        if ref_num > len(citations):
            citations.append(Citation(
                index=ref_num,
                source=f"Source {ref_num}",
            ))
    
    return normalized, citations


def format_findings(findings: list[str]) -> str:
    """Format findings as bullet list."""
    if not findings:
        return "No specific findings documented."
    return "\n".join(f"- {finding}" for finding in findings)


def format_recommendations(recommendations: list[str]) -> str:
    """Format recommendations as numbered list."""
    if not recommendations:
        return "No specific recommendations."
    return "\n".join(f"{i+1}. {rec}" for i, rec in enumerate(recommendations))


def format_citations(citations: list[Citation]) -> str:
    """Format citations as bibliography."""
    if not citations:
        return "No citations."
    return "\n".join(c.format() for c in sorted(citations, key=lambda x: x.index))


def format_metadata_table(metadata: ResearchMetadata) -> str:
    """Format metadata as markdown table."""
    return f"""| Field | Value |
|-------|-------|
| Research Mode | {metadata.mode} |
| Model | {metadata.model} |
| Duration | {metadata.duration_formatted} |
| Cost | {metadata.cost_formatted} |
| Job ID | {metadata.job_id} |
| Completed | {metadata.timestamp_formatted} |"""


def format_result(result: RawResult) -> str:
    """
    Format a raw research result into markdown following the template.
    
    Preserves all inline citations from the source material and normalizes
    citation formats (markdown links become numeric references).
    
    Args:
        result: Raw research result with all components
    
    Returns:
        Formatted markdown string
    
    Raises:
        ValueError: If result has empty title
    
    Note:
        Citations in the bibliography may not all appear in the text body.
        This is valid - the bibliography includes all consulted sources.
    """
    # Validate required fields
    if not result.title or not result.title.strip():
        raise ValueError("Result title cannot be empty")
    
    # Process text fields to extract/normalize citations
    summary_normalized, summary_citations = extract_citations(result.summary or "")
    analysis_normalized, analysis_citations = extract_citations(result.analysis or "")
    
    # Start with all original citations
    all_citations = result.citations.copy()
    
    # Add any new citations found in text (avoiding duplicates)
    for c in summary_citations + analysis_citations:
        if not any(existing.url == c.url and existing.source == c.source 
                   for existing in all_citations):
            c.index = len(all_citations) + 1
            all_citations.append(c)
    
    # Process findings
    findings_processed = []
    for finding in result.findings:
        normalized, _ = extract_citations(finding)
        findings_processed.append(normalized)
    
    # Process recommendations
    recs_processed = []
    for rec in result.recommendations:
        normalized, _ = extract_citations(rec)
        recs_processed.append(normalized)
    
    # Build the formatted output
    output = f"""# {result.title}

## Summary

{summary_normalized or "No summary provided."}

## Key Findings

{format_findings(findings_processed)}

## Analysis

{analysis_normalized or "No analysis provided."}

## Recommendations

{format_recommendations(recs_processed)}

## Citations

{format_citations(all_citations)}

---

{format_metadata_table(result.metadata)}
"""
    
    return output


def load_template(template_path: Optional[Path] = None) -> str:
    """Load the report template."""
    if template_path is None:
        template_path = Path(__file__).parent.parent / "templates" / "research_report.md"
    
    if template_path.exists():
        return template_path.read_text()
    
    # Fallback minimal template
    return """# {title}

## Summary
{summary}

## Findings
{findings}

## Citations
{citations}
"""


def count_citations(text: str) -> int:
    """Count the number of citation references in text."""
    pattern = r'\[\d+\]'
    return len(re.findall(pattern, text))


def validate_citations(formatted: str, original_citations: list[Citation]) -> bool:
    """
    Validate that all original citations are preserved in formatted output.
    
    Returns True if all citations are present.
    """
    for citation in original_citations:
        if f"[{citation.index}]" not in formatted:
            return False
    return True
