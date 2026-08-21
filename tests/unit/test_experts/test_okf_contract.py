"""Offline conformance tests for the published OKF 0.2 form contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import deepr.experts.okf_contract as okf_contract
from deepr.experts.okf_contract import (
    OKF_VERSION,
    parse_markdown_frontmatter,
    read_bounded_markdown_bundle,
    validate_okf_bundle,
    validate_okf_documents,
)

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "standards"


def _violation_codes(result) -> set[str]:
    return {violation.code for violation in result.violations}


def test_fixture_manifest_pins_the_reviewed_okf_spec_revision():
    manifest = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    okf = manifest["standards"][0]

    assert manifest["schema_version"] == "deepr-standards-fixture-manifest-v1"
    assert okf["version"] == OKF_VERSION
    assert okf["canonical_identifier"].endswith("3fcbb9f828c2f23d109c855ee403c3a4c81f3a96/okf/SPEC.md")
    assert okf["sha256"] == "5a3311d270bebb16d558010e75064f5b75323f284992641732b1c8097511f948"


def test_pinned_okf_0_2_fixture_is_conformant_and_preserves_nested_yaml():
    fixture = FIXTURE_ROOT / "okf-0.2" / "valid"

    result = validate_okf_bundle(fixture)
    parsed = parse_markdown_frontmatter((fixture / "concepts" / "orders.md").read_text(encoding="utf-8"))

    assert result.valid, result.violations
    assert result.declared_version == OKF_VERSION
    assert parsed.fields["fixture_extension"] == {"preserved": True}
    assert parsed.fields["verified"]["by"] == "process:fixture-review"


def test_pinned_legacy_fixture_detects_reserved_file_and_frontmatter_placement_violations():
    result = validate_okf_bundle(FIXTURE_ROOT / "okf-0.2" / "legacy-invalid")

    assert not result.valid
    assert {
        "concept_frontmatter",
        "index_frontmatter_position",
        "log_frontmatter",
    } <= _violation_codes(result)


def test_index_is_optional_and_unknown_concept_fields_do_not_fail(tmp_path):
    (tmp_path / "concept.md").write_text(
        "---\ntype: Custom Type\nunknown:\n  nested: [one, two]\n---\n\nSee [missing](missing.md).\n",
        encoding="utf-8",
    )

    result = validate_okf_bundle(tmp_path)

    assert result.valid, result.violations
    assert result.declared_version is None


def test_concept_requires_frontmatter_on_first_line_and_non_empty_type(tmp_path):
    (tmp_path / "comment-first.md").write_text(
        "<!-- generated -->\n---\ntype: Reference\n---\nBody\n",
        encoding="utf-8",
    )
    (tmp_path / "missing-type.md").write_text("---\ntitle: Missing type\n---\nBody\n", encoding="utf-8")

    result = validate_okf_bundle(tmp_path)

    assert _violation_codes(result) == {"concept_frontmatter", "concept_type"}


def test_malformed_or_unsafe_yaml_fails_closed(tmp_path):
    (tmp_path / "malformed.md").write_text("---\ntype: [unterminated\n---\nBody\n", encoding="utf-8")
    (tmp_path / "unsafe.md").write_text(
        "---\ntype: !!python/object/apply:os.system ['echo unsafe']\n---\nBody\n",
        encoding="utf-8",
    )

    result = validate_okf_bundle(tmp_path)

    assert not result.valid
    assert _violation_codes(result) == {"concept_frontmatter"}


def test_yaml_aliases_and_pathological_scalars_fail_closed(tmp_path):
    (tmp_path / "alias.md").write_text(
        "---\ntype: Reference\nloop: &loop [*loop]\n---\nBody\n",
        encoding="utf-8",
    )
    (tmp_path / "large-integer.md").write_text(
        f"---\ntype: Reference\nvalue: {'9' * 5_000}\n---\nBody\n",
        encoding="utf-8",
    )

    result = validate_okf_bundle(tmp_path)

    assert not result.valid
    assert _violation_codes(result) == {"concept_frontmatter"}


def test_bounded_noncyclic_yaml_alias_is_accepted(tmp_path):
    alias_path = tmp_path / "alias.md"
    alias_path.write_text(
        "---\ntype: Reference\nshared: &shared [one, two]\ncopy: *shared\n---\nBody\n",
        encoding="utf-8",
    )

    result = validate_okf_bundle(tmp_path)
    parsed = parse_markdown_frontmatter(alias_path.read_text(encoding="utf-8"))

    assert result.valid, result.violations
    assert parsed.error is None
    assert parsed.fields["copy"] == ["one", "two"]


@pytest.mark.parametrize(
    "extension",
    [
        "!!pairs\n  - key: value",
        "!!omap\n  - key: value",
        "!!set\n  ? key",
    ],
    ids=["pairs", "ordered-map", "set"],
)
def test_non_json_yaml_containers_fail_closed(extension):
    document = f"---\ntype: Reference\nextension: {extension}\n---\nBody\n"

    parsed = parse_markdown_frontmatter(document)
    result = validate_okf_documents({"concept.md": document})

    assert parsed.error is not None
    assert "unsupported YAML container" in parsed.error
    assert _violation_codes(result) == {"concept_frontmatter"}


def test_bounded_markdown_reader_rejects_per_file_limit_before_read(tmp_path, monkeypatch):
    document = "---\ntype: Reference\n---\n" + ("x" * 64)
    (tmp_path / "large.md").write_text(document, encoding="utf-8")
    monkeypatch.setattr(okf_contract, "OKF_MAX_MARKDOWN_FILE_BYTES", len(document.encode("utf-8")) - 1)
    monkeypatch.setattr(okf_contract, "OKF_MAX_MARKDOWN_TOTAL_BYTES", len(document.encode("utf-8")) * 2)
    monkeypatch.setattr(Path, "open", lambda *_args, **_kwargs: pytest.fail("oversized file was opened"))

    result = read_bounded_markdown_bundle(tmp_path)

    assert not result.valid
    assert {violation.code for violation in result.violations} == {"markdown_file_size_limit"}
    assert result.documents == ()


def test_bounded_markdown_reader_rejects_aggregate_limit_before_read(tmp_path, monkeypatch):
    first = "---\ntype: Reference\n---\nFirst\n"
    second = "---\ntype: Reference\n---\nSecond\n"
    (tmp_path / "first.md").write_text(first, encoding="utf-8")
    (tmp_path / "second.md").write_text(second, encoding="utf-8")
    total_bytes = len(first.encode("utf-8")) + len(second.encode("utf-8"))
    monkeypatch.setattr(okf_contract, "OKF_MAX_MARKDOWN_FILE_BYTES", total_bytes)
    monkeypatch.setattr(okf_contract, "OKF_MAX_MARKDOWN_TOTAL_BYTES", total_bytes - 1)
    monkeypatch.setattr(Path, "open", lambda *_args, **_kwargs: pytest.fail("oversized bundle was opened"))

    result = read_bounded_markdown_bundle(tmp_path)

    assert not result.valid
    assert {violation.code for violation in result.violations} == {"markdown_total_size_limit"}
    assert result.documents == ()


def test_bounded_markdown_reader_rejects_file_count_limit(tmp_path, monkeypatch):
    (tmp_path / "first.md").write_text("---\ntype: Reference\n---\nFirst\n", encoding="utf-8")
    (tmp_path / "second.md").write_text("---\ntype: Reference\n---\nSecond\n", encoding="utf-8")
    monkeypatch.setattr(okf_contract, "OKF_MAX_MARKDOWN_FILES", 1)

    result = read_bounded_markdown_bundle(tmp_path)

    assert not result.valid
    assert {violation.code for violation in result.violations} == {"markdown_file_count_limit"}
    assert result.documents == ()


def test_nested_index_frontmatter_and_log_order_fail(tmp_path):
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "index.md").write_text('---\nokf_version: "0.2"\n---\n# Nested\n', encoding="utf-8")
    (tmp_path / "log.md").write_text(
        "# Log\n\n## 2026-08-19\n\n* Older\n\n## 2026-08-20\n\n* Newer\n",
        encoding="utf-8",
    )

    result = validate_okf_bundle(tmp_path)

    assert _violation_codes(result) == {"nested_index_frontmatter", "log_date_order"}


def test_log_rejects_impossible_dates_and_ignores_fenced_headings(tmp_path):
    (tmp_path / "log.md").write_text(
        "# Log\n\n```markdown\n## Not a log date\n```\n\n   ## 2026-02-29\n\n* Impossible\n",
        encoding="utf-8",
    )

    result = validate_okf_bundle(tmp_path)

    assert _violation_codes(result) == {"log_date_heading"}


def test_root_index_rejects_non_target_version(tmp_path):
    (tmp_path / "index.md").write_text('---\nokf_version: "0.1"\n---\n# Index\n', encoding="utf-8")

    result = validate_okf_bundle(tmp_path)

    assert not result.valid
    assert result.declared_version == "0.1"
    assert _violation_codes(result) == {"okf_version"}


def test_root_index_requires_version_to_be_a_string(tmp_path):
    (tmp_path / "index.md").write_text("---\nokf_version: 0.2\n---\n# Index\n", encoding="utf-8")

    result = validate_okf_bundle(tmp_path)

    assert not result.valid
    assert result.declared_version is None
    assert _violation_codes(result) == {"okf_version"}


def test_in_memory_validation_rejects_paths_outside_bundle():
    result = validate_okf_documents(
        {
            "../outside.md": "---\ntype: Reference\n---\nBody\n",
            "C:/outside.md": "---\ntype: Reference\n---\nBody\n",
            "concepts/NUL.md": "---\ntype: Reference\n---\nBody\n",
            "concepts/claim.md:stream": "---\ntype: Reference\n---\nBody\n",
            "concepts/./claim.md": "---\ntype: Reference\n---\nBody\n",
        }
    )

    assert not result.valid
    assert _violation_codes(result) == {"path_outside_bundle"}


def test_in_memory_validation_rejects_portable_path_collisions():
    result = validate_okf_documents(
        {
            "concepts/Claim.md": "---\ntype: Reference\n---\nFirst\n",
            "concepts\\claim.md": "---\ntype: Reference\n---\nSecond\n",
        }
    )

    assert not result.valid
    assert _violation_codes(result) == {"path_collision"}
