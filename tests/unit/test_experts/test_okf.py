"""Tests for OKF export as a regenerated derived view."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from filelock import Timeout as FileLockTimeout

import deepr.experts.okf_contract as okf_contract_module
import deepr.experts.okf_publication as okf_publication_module
from deepr.core.contracts import ExpertManifest, Gap
from deepr.experts.beliefs import Belief, BeliefStore
from deepr.experts.okf import OKF_MARKER, build_okf_bundle, build_okf_ingestion_corpus, write_okf_bundle
from deepr.experts.okf_contract import (
    OKF_VERSION,
    parse_markdown_frontmatter,
    validate_okf_bundle,
    validate_okf_documents,
)
from deepr.experts.profile import ExpertProfile


def _profile() -> ExpertProfile:
    return ExpertProfile(
        name="OKF Expert",
        vector_store_id="vs-okf",
        description="Portable expert knowledge",
        domain="ai",
    )


def _store(tmp_path) -> BeliefStore:
    return BeliefStore("OKF Expert", storage_dir=tmp_path / "beliefs")


def _manifest(*gaps: Gap) -> ExpertManifest:
    return ExpertManifest(expert_name="OKF Expert", domain="ai", gaps=list(gaps))


def test_okf_bundle_contains_required_views_and_marker(tmp_path):
    store = _store(tmp_path)
    store.add_belief(
        Belief(
            claim="Local model admission requires measured evidence",
            confidence=0.9,
            domain="capacity",
            evidence_refs=["eval:local_compare_latest"],
            trust_class="secondary",
        ),
        check_conflicts=False,
    )
    gap = Gap.create("Plan quota adapters need live probes", questions=["Which CLI exposes quota state?"], priority=5)

    bundle = build_okf_bundle(_profile(), store, manifest=_manifest(gap))

    assert {"index.md", "gaps.md", "contested.md", "log.md", "llms.txt"} <= set(bundle.files)
    assert bundle.concept_count == 1
    assert bundle.gap_count == 1
    assert OKF_MARKER in bundle.files["index.md"]
    assert "Local model admission requires measured evidence" in bundle.files["index.md"]
    assert "Plan quota adapters need live probes" in bundle.files["gaps.md"]
    concept = bundle.files[next(path for path in bundle.files if path.startswith("concepts/"))]
    assert "`eval:local_compare_latest`" in concept
    assert "deepr.okf.concept" in concept
    index = parse_markdown_frontmatter(bundle.files["index.md"])
    assert index.fields == {"okf_version": OKF_VERSION}
    assert not parse_markdown_frontmatter(bundle.files["log.md"]).present
    concept_frontmatter = parse_markdown_frontmatter(concept)
    assert concept_frontmatter.fields["generated"]["by"] == "process:deepr-export-okf"
    assert concept_frontmatter.fields["sources"][0]["resource"] == "eval:local_compare_latest"
    assert concept_frontmatter.fields["deepr"]["evidence_refs"] == ["eval:local_compare_latest"]


def test_okf_bundle_is_byte_stable_for_unchanged_store(tmp_path):
    store = _store(tmp_path)
    store.add_belief(Belief("Stable belief", 0.8, domain="ai"), check_conflicts=False)
    profile = _profile()
    manifest = _manifest()

    first = build_okf_bundle(profile, store, manifest=manifest)
    second = build_okf_bundle(profile, store, manifest=manifest)

    assert first.files == second.files
    assert first.as_of == second.as_of


def test_okf_as_of_includes_grounding_verification_event(tmp_path):
    store = _store(tmp_path)
    belief = Belief(
        "Verification is newer than the claim",
        0.8,
        updated_at=datetime(2026, 8, 19, 10, 0, tzinfo=UTC),
        grounding_assurance="cross_vendor",
        grounding_verified_at=datetime(2099, 8, 20, 12, 30, tzinfo=UTC),
    )
    store.beliefs[belief.id] = belief

    bundle = build_okf_bundle(_profile(), store, manifest=_manifest())

    assert bundle.as_of == "2099-08-20T12:30:00+00:00"


def test_okf_generated_time_includes_gap_and_edge_changes(tmp_path):
    store = _store(tmp_path)
    first, _ = store.add_belief(Belief("First", 0.8, domain="ai"), check_conflicts=False)
    second, _ = store.add_belief(Belief("Second", 0.8, domain="ai"), check_conflicts=False)
    edge = store.add_edge(first.id, second.id, "supports")
    edge.created_at = datetime(2098, 8, 20, tzinfo=UTC)
    gap = Gap.create("Future gap")
    gap.identified_at = datetime(2099, 8, 20, tzinfo=UTC)

    bundle = build_okf_bundle(_profile(), store, manifest=_manifest(gap))
    concept = parse_markdown_frontmatter(bundle.files[f"concepts/ai-{first.id}.md"])
    gaps = parse_markdown_frontmatter(bundle.files["gaps.md"])

    assert bundle.as_of == "2099-08-20T00:00:00+00:00"
    assert concept.fields["generated"]["at"] == bundle.as_of
    assert gaps.fields["generated"]["at"] == bundle.as_of


def test_okf_concept_pages_encode_typed_edges_as_relative_links(tmp_path):
    store = _store(tmp_path)
    source, _ = store.add_belief(Belief("A supports B", 0.8, domain="ai"), check_conflicts=False)
    target, _ = store.add_belief(Belief("B is useful", 0.7, domain="ai"), check_conflicts=False)
    store.add_edge(source.id, target.id, "supports", provenance="unit-test")

    bundle = build_okf_bundle(_profile(), store, manifest=_manifest())
    source_page = bundle.files[f"concepts/ai-{source.id}.md"]

    assert "supports:" in source_page
    assert f"./ai-{target.id}.md" in source_page
    assert "`unit-test`" in source_page


def test_okf_contested_view_surfaces_open_contradictions(tmp_path):
    store = _store(tmp_path)
    existing, _ = store.add_belief(Belief("Policy A is mandatory", 0.8, domain="policy"), check_conflicts=False)
    store.add_contested_belief(Belief("Policy A is optional", 0.7, domain="policy"), [existing])

    bundle = build_okf_bundle(_profile(), store, manifest=_manifest())

    assert bundle.contested_count == 1
    assert "Policy A is mandatory" in bundle.files["contested.md"]
    assert "Policy A is optional" in bundle.files["contested.md"]
    assert "contested:absorb" in bundle.files["contested.md"]
    assert "Open contested claims: 1" in bundle.files["index.md"]


def test_okf_log_normalizes_multiline_canonical_event_text(tmp_path):
    store = _store(tmp_path)
    store.add_belief(Belief("Claim line\n## 2026-99-99", 0.8, domain="ai"), check_conflicts=False)

    bundle = build_okf_bundle(_profile(), store, manifest=_manifest())
    validation = validate_okf_documents(bundle.files)

    assert validation.valid, validation.violations
    assert "Claim line ## 2026-99-99" in bundle.files["log.md"]


def test_write_okf_bundle_refuses_root_without_publication_manifest(tmp_path):
    store = _store(tmp_path)
    store.add_belief(Belief("Portable belief", 0.8, domain="ai"), check_conflicts=False)
    bundle = build_okf_bundle(_profile(), store, manifest=_manifest())
    output = tmp_path / "okf"
    output.mkdir()
    (output / "index.md").write_text("# Hand edited\n", encoding="utf-8")

    with pytest.raises(ValueError, match="exact Deepr publication manifest"):
        write_okf_bundle(bundle, output)

    result = write_okf_bundle(bundle, output, force=True)
    assert "index.md" in result.files
    assert OKF_MARKER in (output / "index.md").read_text(encoding="utf-8")


def test_write_okf_bundle_replaces_complete_dedicated_root(tmp_path):
    store = _store(tmp_path)
    stored, _ = store.add_belief(Belief("Obsolete portable belief", 0.8, domain="ai"), check_conflicts=False)
    output = tmp_path / "okf"
    write_okf_bundle(build_okf_bundle(_profile(), store, manifest=_manifest()), output)
    stale_path = output / f"concepts/ai-{stored.id}.md"
    unrelated_empty = output / "scratch"
    unrelated_empty.mkdir()

    store.beliefs.clear()
    with pytest.raises(ValueError, match="dedicated derived export root"):
        write_okf_bundle(build_okf_bundle(_profile(), store, manifest=_manifest()), output)

    write_okf_bundle(build_okf_bundle(_profile(), store, manifest=_manifest()), output, force=True)

    assert not stale_path.exists()
    assert not (output / "concepts").exists()
    assert not unrelated_empty.exists()


def test_write_okf_bundle_refuses_unmanaged_markdown_in_export_root(tmp_path):
    bundle = build_okf_bundle(_profile(), _store(tmp_path), manifest=_manifest())
    output = tmp_path / "okf"
    write_okf_bundle(bundle, output)
    hand_file = output / "notes.md"
    hand_file.write_text("# Unmanaged\n", encoding="utf-8")

    with pytest.raises(ValueError, match="unmanaged Markdown"):
        write_okf_bundle(bundle, output)

    assert hand_file.read_text(encoding="utf-8") == "# Unmanaged\n"


def test_write_okf_bundle_refuses_nonconformant_generated_content_before_writing(tmp_path):
    store = _store(tmp_path)
    bundle = build_okf_bundle(_profile(), store, manifest=_manifest())
    invalid = replace(
        bundle,
        files={
            **bundle.files,
            "concepts/broken.md": "<!-- misplaced -->\n---\ntype: Reference\n---\nBroken\n",
        },
    )
    output = tmp_path / "invalid-okf"

    with pytest.raises(ValueError, match=r"does not conform to OKF 0\.2"):
        write_okf_bundle(invalid, output)

    assert not output.exists()


def test_write_okf_bundle_rejects_windows_absolute_path_before_writing(tmp_path):
    bundle = build_okf_bundle(_profile(), _store(tmp_path), manifest=_manifest())
    invalid = replace(
        bundle,
        files={**bundle.files, "C:/outside.md": "---\ntype: Reference\n---\nBroken\n"},
    )
    output = tmp_path / "invalid-okf"

    with pytest.raises(ValueError, match="path_outside_bundle"):
        write_okf_bundle(invalid, output)

    assert not output.exists()


def test_write_okf_bundle_requires_marker_on_every_generated_file(tmp_path):
    bundle = build_okf_bundle(_profile(), _store(tmp_path), manifest=_manifest())
    invalid = replace(bundle, files={**bundle.files, "metadata.json": "{}\n"})
    output = tmp_path / "invalid-okf"

    with pytest.raises(ValueError, match="lack the Deepr ownership marker"):
        write_okf_bundle(invalid, output)

    assert not output.exists()


def test_write_okf_bundle_translates_lock_timeout(tmp_path, monkeypatch):
    class _BlockedLock:
        def __enter__(self):
            raise FileLockTimeout("blocked.lock")

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(okf_publication_module, "FileLock", lambda *_args, **_kwargs: _BlockedLock())
    bundle = build_okf_bundle(_profile(), _store(tmp_path), manifest=_manifest())

    with pytest.raises(ValueError, match="Timed out waiting for the OKF export lock"):
        write_okf_bundle(bundle, tmp_path / "okf")


def test_written_bundle_passes_offline_okf_0_2_conformance(tmp_path):
    store = _store(tmp_path)
    store.add_belief(
        Belief(
            "Verified portable belief",
            0.8,
            domain="ai",
            evidence_refs=["https://example.test/evidence"],
            grounding_assurance="cross_vendor",
            grounding_verified_at=datetime(2026, 8, 20, 12, 30, tzinfo=UTC),
        ),
        check_conflicts=False,
    )
    output = tmp_path / "okf"
    write_okf_bundle(build_okf_bundle(_profile(), store, manifest=_manifest()), output)

    result = validate_okf_bundle(output)
    concept = next((output / "concepts").glob("*.md"))
    fields = parse_markdown_frontmatter(concept.read_text(encoding="utf-8")).fields

    assert result.valid, result.violations
    assert result.declared_version == OKF_VERSION
    assert fields["verified"]["by"] == "process:deepr-cross-vendor-checker"
    assert fields["verified"]["at"] == "2026-08-20T12:30:00+00:00"


def test_okf_does_not_invent_verification_time_for_legacy_assurance(tmp_path):
    store = _store(tmp_path)
    stored, _ = store.add_belief(
        Belief(
            "Legacy verified belief",
            0.8,
            domain="ai",
            grounding_assurance="cross_vendor",
        ),
        check_conflicts=False,
    )

    bundle = build_okf_bundle(_profile(), store, manifest=_manifest())
    concept = parse_markdown_frontmatter(bundle.files[f"concepts/ai-{stored.id}.md"])

    assert "verified" not in concept.fields


def test_build_okf_ingestion_corpus_uses_all_non_reserved_concept_documents(tmp_path):
    store = _store(tmp_path)
    store.add_belief(
        Belief(
            claim="OKF import must verify claims before persistence",
            confidence=0.85,
            domain="interop",
            evidence_refs=["okf:concept"],
        ),
        check_conflicts=False,
    )
    bundle = build_okf_bundle(_profile(), store, manifest=_manifest())
    output = tmp_path / "okf"
    write_okf_bundle(bundle, output)

    corpus = build_okf_ingestion_corpus(output)

    assert corpus.concept_count == 3
    assert corpus.report_id.startswith("okf:okf:")
    assert "OKF import must verify claims before persistence" in corpus.report_text
    assert "sources:" in corpus.report_text
    assert "[Back to index](../index.md)" in corpus.report_text
    assert "gaps.md" in corpus.files
    assert "contested.md" in corpus.files


def test_build_okf_ingestion_corpus_accepts_mixed_yaml_mapping_keys(tmp_path):
    concept = tmp_path / "concept.md"
    concept.write_text(
        "---\ntype: Reference\nextension:\n  1: one\n  text: two\n  2026-08-20: dated\n---\nBody\n",
        encoding="utf-8",
    )

    corpus = build_okf_ingestion_corpus(tmp_path)

    assert corpus.concept_count == 1
    assert "1: one" in corpus.report_text
    assert "'2026-08-20': dated" in corpus.report_text


def test_build_okf_ingestion_corpus_rejects_bounds_before_parsing(tmp_path, monkeypatch):
    (tmp_path / "concept.md").write_text(
        "---\ntype: Reference\n---\n" + ("x" * 64),
        encoding="utf-8",
    )
    monkeypatch.setattr(okf_contract_module, "OKF_MAX_MARKDOWN_FILE_BYTES", 32)

    with pytest.raises(ValueError) as error:
        build_okf_ingestion_corpus(tmp_path)

    assert str(error.value) == (
        "Cannot ingest OKF bundle: concept.md [markdown_file_size_limit]: File exceeds the maximum of 32 bytes"
    )


def test_build_okf_ingestion_corpus_rejects_hard_form_violations_as_one_error(tmp_path):
    (tmp_path / "valid.md").write_text("---\ntype: Custom Type\nextension: allowed\n---\nValid\n", encoding="utf-8")
    (tmp_path / "malformed.md").write_text("---\ntype: [unterminated\n---\nBody\n", encoding="utf-8")
    (tmp_path / "log.md").write_text("---\ntype: Reference\n---\n# Log\n", encoding="utf-8")

    with pytest.raises(ValueError) as error:
        build_okf_ingestion_corpus(tmp_path)

    assert str(error.value).startswith("Cannot ingest OKF bundle: log.md [log_frontmatter]")
    assert "malformed.md [concept_frontmatter]" in str(error.value)


def test_build_okf_ingestion_corpus_preserves_extensions_and_broken_links(tmp_path):
    (tmp_path / "concept.md").write_text(
        "---\ntype: Custom Type\nextension:\n  enabled: true\n---\nSee [missing](missing.md).\n",
        encoding="utf-8",
    )

    corpus = build_okf_ingestion_corpus(tmp_path)

    assert corpus.concept_count == 1
    assert "extension:" in corpus.report_text
    assert "[missing](missing.md)" in corpus.report_text


def test_build_okf_ingestion_corpus_rejects_bundle_without_concepts(tmp_path):
    (tmp_path / "index.md").write_text("# Not a concept\n", encoding="utf-8")

    with pytest.raises(ValueError, match="No OKF concept"):
        build_okf_ingestion_corpus(tmp_path)
