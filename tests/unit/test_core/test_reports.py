"""Tests for report generation module.

Requirements: 1.3 - Test Coverage
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deepr.core.reports import ReportGenerator


class TestReportGeneratorInit:
    """Tests for ReportGenerator initialization."""

    def test_default_initialization(self):
        """Should initialize with defaults."""
        generator = ReportGenerator()

        assert generator.strip_citations is True
        assert generator.default_formats == ["txt", "md", "json", "docx"]
        assert generator.converter is not None

    def test_custom_initialization(self):
        """Should initialize with custom settings."""
        generator = ReportGenerator(
            generate_pdf=True,
            strip_citations=False,
            default_formats=["txt", "md"]
        )

        assert generator.strip_citations is False
        assert generator.default_formats == ["txt", "md"]


class TestExtractTextFromResponse:
    """Tests for extract_text_from_response method."""

    def test_extract_from_empty_response(self):
        """Should return empty string for empty response."""
        generator = ReportGenerator()
        response = MagicMock()
        response.output = None

        result = generator.extract_text_from_response(response)

        assert result == ""

    def test_extract_from_message_output(self):
        """Should extract text from message output."""
        generator = ReportGenerator()
        response = MagicMock()
        response.output = [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": "First paragraph."},
                    {"type": "output_text", "text": "Second paragraph."}
                ]
            }
        ]

        result = generator.extract_text_from_response(response)

        assert "First paragraph." in result
        assert "Second paragraph." in result

    def test_extract_from_text_type(self):
        """Should extract text from 'text' type content."""
        generator = ReportGenerator()
        response = MagicMock()
        response.output = [
            {
                "type": "message",
                "content": [
                    {"type": "text", "text": "Text content."}
                ]
            }
        ]

        result = generator.extract_text_from_response(response)

        assert "Text content." in result

    def test_extract_ignores_non_text_content(self):
        """Should ignore non-text content types."""
        generator = ReportGenerator()
        response = MagicMock()
        response.output = [
            {
                "type": "message",
                "content": [
                    {"type": "image", "data": "..."},
                    {"type": "output_text", "text": "Text content."}
                ]
            }
        ]

        result = generator.extract_text_from_response(response)

        assert result == "Text content."

    def test_extract_from_multiple_messages(self):
        """Should extract text from multiple message blocks."""
        generator = ReportGenerator()
        response = MagicMock()
        response.output = [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "First message."}]
            },
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "Second message."}]
            }
        ]

        result = generator.extract_text_from_response(response)

        assert "First message." in result
        assert "Second message." in result

    def test_extract_ignores_non_message_blocks(self):
        """Should ignore non-message blocks."""
        generator = ReportGenerator()
        response = MagicMock()
        response.output = [
            {"type": "tool_call", "tool": "search"},
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "Text content."}]
            }
        ]

        result = generator.extract_text_from_response(response)

        assert result == "Text content."


class TestGenerateReports:
    """Tests for generate_reports method."""

    @pytest.mark.asyncio
    async def test_generate_default_formats(self):
        """Should generate default formats."""
        generator = ReportGenerator(default_formats=["txt", "md"])

        with patch.object(generator.converter, 'generate_all_formats', new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = {
                "txt": b"text content",
                "md": b"markdown content",
                "json": b"json content",
                "docx": b"docx content"
            }

            reports = await generator.generate_reports(
                text="Test content",
                title="Test Report"
            )

            # Should only include default formats
            assert "txt" in reports
            assert "md" in reports
            assert "json" not in reports
            assert "docx" not in reports

    @pytest.mark.asyncio
    async def test_generate_custom_formats(self):
        """Should generate custom formats."""
        generator = ReportGenerator()

        with patch.object(generator.converter, 'generate_all_formats', new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = {
                "txt": b"text content",
                "md": b"markdown content",
                "json": b"json content",
                "docx": b"docx content"
            }

            reports = await generator.generate_reports(
                text="Test content",
                title="Test Report",
                formats=["json"]
            )

            # Should only include requested formats
            assert "json" in reports
            assert len(reports) == 1

    @pytest.mark.asyncio
    async def test_passes_strip_citations(self):
        """Should pass strip_citations setting to converter."""
        generator = ReportGenerator(strip_citations=False)

        with patch.object(generator.converter, 'generate_all_formats', new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = {"txt": b"content"}

            await generator.generate_reports(
                text="Test content",
                title="Test Report",
                formats=["txt"]
            )

            mock_gen.assert_called_once_with(
                text="Test content",
                title="Test Report",
                strip_citations=False
            )


class TestGenerateSingleFormat:
    """Tests for generate_single_format method."""

    @pytest.mark.asyncio
    async def test_generate_single_txt(self):
        """Should generate single txt format."""
        generator = ReportGenerator()

        with patch.object(generator.converter, 'generate_all_formats', new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = {"txt": b"text content"}

            result = await generator.generate_single_format(
                text="Test content",
                title="Test Report",
                format_type="txt"
            )

            assert result == b"text content"

    @pytest.mark.asyncio
    async def test_generate_single_returns_empty_for_missing(self):
        """Should return empty bytes if format not available."""
        generator = ReportGenerator()

        with patch.object(generator.converter, 'generate_all_formats', new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = {"txt": b"text content"}

            result = await generator.generate_single_format(
                text="Test content",
                title="Test Report",
                format_type="pdf"
            )

            assert result == b""
