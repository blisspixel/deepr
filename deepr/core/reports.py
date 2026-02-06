"""Report generation and formatting."""

from typing import Dict, List, Optional

from ..formatting.converters import ReportConverter
from ..providers.base import ResearchResponse


class ReportGenerator:
    """Generates reports in multiple formats from research results."""

    def __init__(
        self,
        generate_pdf: bool = False,
        strip_citations: bool = True,
        default_formats: Optional[List[str]] = None,
    ):
        """
        Initialize report generator.

        Args:
            generate_pdf: Whether to generate PDF outputs
            strip_citations: Whether to strip inline citations
            default_formats: Default formats to generate
        """
        self.converter = ReportConverter(generate_pdf=generate_pdf)
        self.strip_citations = strip_citations
        self.default_formats = default_formats or ["txt", "md", "json", "docx"]

    def extract_text_from_response(self, response: ResearchResponse) -> str:
        """
        Extract text content from provider response.

        Args:
            response: Research response from provider

        Returns:
            Extracted text content
        """
        if not response.output:
            return ""

        text_parts = []

        for block in response.output:
            if block.get("type") == "message":
                for content_item in block.get("content", []):
                    if content_item.get("type") in ("output_text", "text"):
                        text_parts.append(content_item.get("text", ""))

        return "\n\n".join(text_parts).strip()

    async def generate_reports(
        self,
        text: str,
        title: str,
        formats: Optional[List[str]] = None,
    ) -> Dict[str, bytes]:
        """
        Generate reports in multiple formats.

        Args:
            text: Raw text content
            title: Report title
            formats: List of formats to generate (default: all)

        Returns:
            Dictionary mapping format names to content bytes
        """
        # Use provided formats or defaults
        requested_formats = formats or self.default_formats

        # Generate all formats
        all_formats = await self.converter.generate_all_formats(
            text=text, title=title, strip_citations=self.strip_citations
        )

        # Filter to requested formats
        return {fmt: content for fmt, content in all_formats.items() if fmt in requested_formats}

    async def generate_single_format(self, text: str, title: str, format_type: str) -> bytes:
        """
        Generate a single report format.

        Args:
            text: Raw text content
            title: Report title
            format_type: Format to generate (txt, md, json, docx, pdf)

        Returns:
            Report content as bytes
        """
        reports = await self.generate_reports(text, title, formats=[format_type])
        return reports.get(format_type, b"")
