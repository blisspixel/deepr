"""Tests for OKF export as a regenerated derived view."""

from __future__ import annotations

import pytest

from deepr.core.contracts import ExpertManifest, Gap
from deepr.experts.beliefs import Belief, BeliefStore
from deepr.experts.okf import OKF_MARKER, build_okf_bundle, write_okf_bundle
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


def test_okf_bundle_is_byte_stable_for_unchanged_store(tmp_path):
    store = _store(tmp_path)
    store.add_belief(Belief("Stable belief", 0.8, domain="ai"), check_conflicts=False)

    first = build_okf_bundle(_profile(), store, manifest=_manifest())
    second = build_okf_bundle(_profile(), store, manifest=_manifest())

    assert first.files == second.files
    assert first.as_of == second.as_of


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


def test_write_okf_bundle_refuses_to_overwrite_hand_edited_file(tmp_path):
    store = _store(tmp_path)
    store.add_belief(Belief("Portable belief", 0.8, domain="ai"), check_conflicts=False)
    bundle = build_okf_bundle(_profile(), store, manifest=_manifest())
    output = tmp_path / "okf"
    output.mkdir()
    (output / "index.md").write_text("# Hand edited\n", encoding="utf-8")

    with pytest.raises(ValueError, match="derived-view marker"):
        write_okf_bundle(bundle, output)

    result = write_okf_bundle(bundle, output, force=True)
    assert "index.md" in result.files
    assert OKF_MARKER in (output / "index.md").read_text(encoding="utf-8")
