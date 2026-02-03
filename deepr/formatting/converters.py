"""Report format conversion utilities."""

import logging
import os
from pathlib import Path
from typing import Dict, Optional
from docx import Document
from .normalize import normalize_markdown
from .style import apply_styles_to_doc, format_paragraph

logger = logging.getLogger(__name__)


class ReportConverter:
    """Convert reports between different formats."""

    def __init__(self, generate_pdf: bool = False):
        """
        Initialize report converter.

        Args:
            generate_pdf: Whether to generate PDF outputs
        """
        self.generate_pdf = generate_pdf

    async def convert_to_docx(
        self, markdown_text: str, title: str, output_path: Optional[str] = None
    ) -> bytes:
        """
        Convert markdown to DOCX format.

        Args:
            markdown_text: Markdown content
            title: Report title
            output_path: Optional path to save file

        Returns:
            DOCX content as bytes
        """
        # Normalize markdown
        normalized = normalize_markdown(markdown_text)

        # Create document
        doc = Document()

        # Add title
        para = doc.add_paragraph(title, style="Heading 1")
        format_paragraph(para, spacing_after=12)

        # Apply styles
        apply_styles_to_doc(doc, normalized)

        # Save to bytes
        if output_path:
            doc.save(output_path)
            with open(output_path, "rb") as f:
                return f.read()
        else:
            # Save to memory
            from io import BytesIO

            buffer = BytesIO()
            doc.save(buffer)
            buffer.seek(0)
            return buffer.read()

    async def convert_to_pdf(self, docx_path: str, pdf_path: Optional[str] = None) -> Optional[bytes]:
        """
        Convert DOCX to PDF format.

        Args:
            docx_path: Path to DOCX file
            pdf_path: Optional path to save PDF

        Returns:
            PDF content as bytes (if pdf_path not provided)
        """
        if not self.generate_pdf:
            return None

        try:
            from docx2pdf import convert

            if pdf_path:
                convert(docx_path, pdf_path)
                with open(pdf_path, "rb") as f:
                    return f.read()
            else:
                # Generate temp path
                temp_pdf = str(Path(docx_path).with_suffix(".pdf"))
                convert(docx_path, temp_pdf)
                with open(temp_pdf, "rb") as f:
                    content = f.read()
                os.remove(temp_pdf)
                return content

        except Exception as e:
            logger.warning("PDF conversion failed: %s", e)
            return None

    async def generate_all_formats(
        self, text: str, title: str, strip_citations: bool = True
    ) -> Dict[str, bytes]:
        """
        Generate all report formats from text.

        Args:
            text: Raw text content
            title: Report title
            strip_citations: Whether to strip inline citations

        Returns:
            Dictionary mapping format names to content bytes
        """
        import json
        import re

        formats = {}

        # Strip citations if requested
        if strip_citations:
            text = self._strip_citations(text)

        # TXT format (raw text)
        formats["txt"] = text.encode("utf-8")

        # Normalize for markdown
        normalized = normalize_markdown(text)

        # MD format (with title)
        md_content = f"# {title}\n\n{normalized}"
        formats["md"] = md_content.encode("utf-8")

        # JSON format (structured)
        json_data = {"title": title, "content": text, "format": "markdown"}
        formats["json"] = json.dumps(json_data, indent=2).encode("utf-8")

        # DOCX format
        formats["docx"] = await self.convert_to_docx(normalized, title)

        # PDF format (if enabled)
        if self.generate_pdf:
            # Need to save DOCX temporarily for PDF conversion
            import tempfile

            with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
                tmp.write(formats["docx"])
                tmp_path = tmp.name

            pdf_content = await self.convert_to_pdf(tmp_path)
            if pdf_content:
                formats["pdf"] = pdf_content

            os.remove(tmp_path)

        return formats

    @staticmethod
    def _strip_citations(text: str) -> str:
        """Remove inline citations from text."""
        # Remove [1], [23], etc.
        text = re.sub(r"\s?\[\d{1,3}\]", "", text)
        # Remove (http://...) parenthetical urls
        text = re.sub(r"\s?\((https?://[^\s)]+)\)", "", text)
        # Remove ^1 ^12 style
        text = re.sub(r"\s?\^\d{1,3}", "", text)
        return text

    @staticmethod
    def extract_references(text: str) -> list:
        """Extract all URLs from text."""
        url_pattern = r"https?://[^\s\)\]]+"
        return sorted(set(re.findall(url_pattern, text)))
