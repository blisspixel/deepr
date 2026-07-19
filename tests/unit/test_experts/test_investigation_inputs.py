from __future__ import annotations

import copy
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

import deepr.experts.investigation.inputs as investigation_inputs
from deepr.experts.investigation.inputs import (
    InputLimits,
    compile_input_bundle,
    materialize_input_context,
    requested_urls,
)
from deepr.experts.investigation.models import InvestigationContractError, validate_input_bundle

NOW = "2026-07-17T00:00:00+00:00"


def test_compile_input_bundle_is_stable_sorted_and_explicit(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "z.md").write_text("zeta", encoding="utf-8")
    (source / "a.py").write_text("print('a')", encoding="utf-8")
    (source / ".env").write_text("TOKEN=secret", encoding="utf-8")
    (source / "image.bin").write_bytes(b"\x00\x01")
    hidden = source / ".cache"
    hidden.mkdir()
    (hidden / "ignored.txt").write_text("ignored", encoding="utf-8")

    first = compile_input_bundle(
        input_root=tmp_path,
        inline_texts=["caller constraint"],
        urls=["HTTPS://Example.com/spec#section", "https://example.com/spec"],
        folders=[source],
        created_at=NOW,
    )
    second = compile_input_bundle(
        input_root=tmp_path,
        inline_texts=["caller constraint"],
        urls=["https://example.com/spec"],
        folders=[source],
        created_at=NOW,
    )

    assert first == second
    assert [item["input_type"] for item in first["items"]] == ["inline_text", "url", "file", "file"]
    assert [item["display_path"] for item in first["items"] if item["input_type"] == "file"] == [
        "source/a.py",
        "source/z.md",
    ]
    assert requested_urls(first) == ("https://example.com/spec",)
    assert [(item["path"], item["reason"]) for item in first["exclusions"]] == [
        ("source/.cache", "excluded_subtree"),
        ("source/.env", "hidden_path"),
        ("source/image.bin", "unsupported_type"),
    ]
    assert first["summary"] == {
        "included_items": 4,
        "included_files": 2,
        "requested_urls": 1,
        "excluded_paths": 3,
        "local_input_bytes": 31,
    }


def test_bundle_rejects_escape_credentials_and_private_url(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("outside", encoding="utf-8")

    with pytest.raises(InvestigationContractError, match="escapes"):
        compile_input_bundle(input_root=tmp_path, files=[outside], created_at=NOW)
    with pytest.raises(InvestigationContractError, match="credentials"):
        compile_input_bundle(input_root=tmp_path, urls=["https://user:pass@example.com/a"], created_at=NOW)
    with pytest.raises(InvestigationContractError, match="non-public"):
        compile_input_bundle(input_root=tmp_path, urls=["http://127.0.0.1/a"], created_at=NOW)


def test_bundle_records_size_and_count_exclusions(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("12345", encoding="utf-8")
    (tmp_path / "b.txt").write_text("67890", encoding="utf-8")
    (tmp_path / "c.txt").write_text("oversized", encoding="utf-8")
    limits = InputLimits(max_files=1, max_file_bytes=5, max_total_bytes=8, max_inline_bytes=8, max_extracted_bytes=32)

    bundle = compile_input_bundle(
        input_root=tmp_path,
        inline_texts=["x"],
        folders=[tmp_path],
        limits=limits,
        created_at=NOW,
    )

    assert [item["display_path"] for item in bundle["items"] if item["input_type"] == "file"] == ["a.txt"]
    assert [(item["path"], item["reason"]) for item in bundle["exclusions"]] == [
        ("b.txt", "file_count_limit"),
        ("c.txt", "oversized_file"),
    ]


def test_materialize_verifies_hash_and_bounds_context(tmp_path: Path) -> None:
    path = tmp_path / "notes.md"
    path.write_text("abcdef", encoding="utf-8")
    limits = InputLimits(max_extracted_bytes=5)
    bundle = compile_input_bundle(
        input_root=tmp_path,
        inline_texts=["xy"],
        files=[path],
        limits=limits,
        created_at=NOW,
    )

    assert materialize_input_context(bundle) == [
        {"ref": "input-0001", "label": "inline-1", "source_class": "caller_supplied", "text": "xy"},
        {
            "ref": "input-0002",
            "label": "notes.md",
            "source_class": "caller_supplied_file",
            "text": "abc",
        },
    ]
    path.write_text("changed", encoding="utf-8")
    with pytest.raises(InvestigationContractError, match="content changed"):
        materialize_input_context(bundle)


def test_bundle_hash_detects_tampering(tmp_path: Path) -> None:
    bundle = compile_input_bundle(input_root=tmp_path, inline_texts=["original"], created_at=NOW)
    tampered = copy.deepcopy(bundle)
    tampered["items"][0]["content"] = "changed"

    with pytest.raises(InvestigationContractError, match="hash does not match"):
        validate_input_bundle(tampered)


def test_input_limits_fail_closed() -> None:
    with pytest.raises(InvestigationContractError, match="positive integer"):
        InputLimits(max_files=0).validated()
    with pytest.raises(InvestigationContractError, match="cannot exceed"):
        InputLimits(max_file_bytes=10, max_total_bytes=5).validated()


def test_oversized_file_is_rejected_before_content_open(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "oversized.txt"
    path.write_bytes(b"x" * 32)

    def fail_open(*_args, **_kwargs):
        raise AssertionError("oversized file content must not be opened")

    monkeypatch.setattr(investigation_inputs.os, "open", fail_open)
    bundle = compile_input_bundle(
        input_root=tmp_path,
        files=[path],
        limits=InputLimits(
            max_file_bytes=8,
            max_total_bytes=16,
            max_extracted_bytes=16,
        ),
        created_at=NOW,
    )

    assert bundle["items"] == []
    assert [(item["path"], item["reason"]) for item in bundle["exclusions"]] == [
        ("oversized.txt", "oversized_file")
    ]


def test_docx_expansion_is_bounded_before_xml_parse(tmp_path: Path) -> None:
    path = tmp_path / "expanded.docx"
    document_xml = (
        '<w:document xmlns:w="urn:test"><w:body><w:p><w:r><w:t>'
        + ("x" * 300_000)
        + "</w:t></w:r></w:p></w:body></w:document>"
    )
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", document_xml)

    bundle = compile_input_bundle(
        input_root=tmp_path,
        files=[path],
        limits=InputLimits(max_extracted_bytes=32),
        created_at=NOW,
    )

    with pytest.raises(InvestigationContractError, match="expansion"):
        materialize_input_context(bundle)


def test_docx_text_is_extracted_inside_byte_ceiling(tmp_path: Path) -> None:
    path = tmp_path / "notes.docx"
    document_xml = (
        '<w:document xmlns:w="urn:test"><w:body><w:p><w:r><w:t>'
        "Bounded document evidence"
        "</w:t></w:r></w:p></w:body></w:document>"
    )
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", document_xml)

    bundle = compile_input_bundle(
        input_root=tmp_path,
        files=[path],
        limits=InputLimits(max_extracted_bytes=12),
        created_at=NOW,
    )

    assert materialize_input_context(bundle) == [
        {
            "ref": "input-0001",
            "label": "notes.docx",
            "source_class": "caller_supplied_file",
            "text": "Bounded docu",
        }
    ]
