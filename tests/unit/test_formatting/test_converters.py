"""Tests for deepr.formatting.converters.ReportConverter."""

from __future__ import annotations

import json
import zipfile

import pytest

from deepr.formatting.converters import ReportConverter

SAMPLE = (
    "# Heading\n\nSome text with a citation [1] and a link (https://example.com/a).\n\n- bullet one\n- bullet two\n"
)


class TestStripCitations:
    def test_strips_bracket_citations(self):
        out = ReportConverter._strip_citations("Fact [1] and another [23] claim.")
        assert "[1]" not in out
        assert "[23]" not in out
        assert "Fact" in out and "claim." in out

    def test_strips_parenthetical_urls(self):
        out = ReportConverter._strip_citations("See it here (https://example.com/x) now.")
        assert "https://example.com/x" not in out
        assert "See it here" in out

    def test_strips_caret_citations(self):
        out = ReportConverter._strip_citations("Claim^1 and claim^42 here.")
        assert "^1" not in out
        assert "^42" not in out


class TestExtractReferences:
    def test_extracts_and_dedupes_sorted(self):
        text = "a https://b.com/2 then https://a.com/1 and https://b.com/2 again"
        refs = ReportConverter.extract_references(text)
        assert refs == ["https://a.com/1", "https://b.com/2"]

    def test_no_urls_returns_empty(self):
        assert ReportConverter.extract_references("no links here") == []


class TestConvertToDocx:
    @pytest.mark.asyncio
    async def test_returns_docx_bytes(self):
        import io

        data = await ReportConverter().convert_to_docx("## Section\n\nBody text.", "My Title")
        assert isinstance(data, bytes)
        assert data[:2] == b"PK"  # DOCX is a zip
        # The title text is embedded in the document.xml part.
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            doc_xml = zf.read("word/document.xml").decode("utf-8")
        assert "My Title" in doc_xml

    @pytest.mark.asyncio
    async def test_writes_to_output_path(self, tmp_path):
        out = tmp_path / "r.docx"
        data = await ReportConverter().convert_to_docx("body", "T", output_path=str(out))
        assert out.exists()
        assert out.read_bytes() == data


def _install_fake_docx2pdf(monkeypatch, *, fail: bool = False):
    """Inject a fake docx2pdf module so the PDF path is exercised offline."""
    import sys
    import types

    mod = types.ModuleType("docx2pdf")

    def convert(src, dst):
        if fail:
            raise RuntimeError("conversion unavailable")
        from pathlib import Path as _P

        _P(dst).write_bytes(b"%PDF-1.4 fake")

    mod.convert = convert
    monkeypatch.setitem(sys.modules, "docx2pdf", mod)


class TestConvertToPdf:
    @pytest.mark.asyncio
    async def test_disabled_returns_none(self, tmp_path):
        # generate_pdf defaults to False -> no conversion attempted.
        assert await ReportConverter().convert_to_pdf(str(tmp_path / "x.docx")) is None

    @pytest.mark.asyncio
    async def test_enabled_with_explicit_pdf_path(self, tmp_path, monkeypatch):
        _install_fake_docx2pdf(monkeypatch)
        docx = tmp_path / "a.docx"
        docx.write_bytes(b"x")
        out = await ReportConverter(generate_pdf=True).convert_to_pdf(str(docx), str(tmp_path / "a.pdf"))
        assert out is not None and out.startswith(b"%PDF")

    @pytest.mark.asyncio
    async def test_enabled_without_pdf_path_uses_temp(self, tmp_path, monkeypatch):
        _install_fake_docx2pdf(monkeypatch)
        docx = tmp_path / "b.docx"
        docx.write_bytes(b"x")
        out = await ReportConverter(generate_pdf=True).convert_to_pdf(str(docx))
        assert out is not None and out.startswith(b"%PDF")
        # The temp pdf beside the docx is cleaned up.
        assert not (tmp_path / "b.pdf").exists()

    @pytest.mark.asyncio
    async def test_conversion_failure_returns_none(self, tmp_path, monkeypatch):
        _install_fake_docx2pdf(monkeypatch, fail=True)
        docx = tmp_path / "c.docx"
        docx.write_bytes(b"x")
        assert await ReportConverter(generate_pdf=True).convert_to_pdf(str(docx)) is None

    @pytest.mark.asyncio
    async def test_generate_all_formats_includes_pdf_when_enabled(self, monkeypatch):
        _install_fake_docx2pdf(monkeypatch)
        formats = await ReportConverter(generate_pdf=True).generate_all_formats(SAMPLE, "T")
        assert "pdf" in formats
        assert formats["pdf"].startswith(b"%PDF")


class TestGenerateAllFormats:
    @pytest.mark.asyncio
    async def test_produces_txt_md_json_docx(self):
        formats = await ReportConverter().generate_all_formats(SAMPLE, "Report Title")
        assert set(formats) >= {"txt", "md", "json", "docx"}
        assert "pdf" not in formats  # generate_pdf is False

        # JSON is well-formed and carries the title.
        parsed = json.loads(formats["json"].decode("utf-8"))
        assert parsed["title"] == "Report Title"
        assert parsed["format"] == "markdown"

        # MD has the title heading.
        assert formats["md"].decode("utf-8").startswith("# Report Title")

        # DOCX is a zip blob.
        assert formats["docx"][:2] == b"PK"

    @pytest.mark.asyncio
    async def test_strip_citations_flag_removes_citation_from_txt(self):
        formats = await ReportConverter().generate_all_formats(SAMPLE, "T", strip_citations=True)
        assert "[1]" not in formats["txt"].decode("utf-8")

    @pytest.mark.asyncio
    async def test_no_strip_keeps_citation(self):
        formats = await ReportConverter().generate_all_formats(SAMPLE, "T", strip_citations=False)
        assert "[1]" in formats["txt"].decode("utf-8")
