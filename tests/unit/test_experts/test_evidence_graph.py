"""The chain from a claim to a passage, stored as edges instead of recomputed.

Every edge here is copied from a field that already existed - corpus_shas on a
finding, supported_by on a position - so the graph is a change of storage, not
a new claim. What it buys is the questions that were expensive across two flat
files: which positions reach no source at all, which evidence nothing uses, and
which passages the claims actually rest on.
"""

from types import SimpleNamespace

from deepr.experts.evidence_graph import (
    EDGE_ANCHORED_IN,
    EDGE_RESTS_ON,
    EvidenceGraph,
    build_graph,
    render_graph,
)


def _finding(finding_id, shas, *, grounded=True, title="", lens="failure"):
    return SimpleNamespace(
        finding_id=finding_id, corpus_shas=list(shas), is_grounded=grounded, title=title or finding_id, lens=lens
    )


def _study(findings, started_at="2026-08-01T00:00:00+00:00"):
    return SimpleNamespace(findings=findings, started_at=started_at)


def _position(question, supported_by, **attrs):
    return SimpleNamespace(question=question, supported_by=list(supported_by), stance="", likelihood="", confidence="", **attrs)


def _entry(sha, publisher="a.org", title=""):
    """A CorpusStore entry, which names the hash `sha256`."""
    return SimpleNamespace(
        sha256=sha, publisher=publisher, origin_key=f"url:{publisher}", title=title, added_at="", fetched_at=""
    )


def _built(**overrides):
    """A small, fully connected expert: one position, two findings, two sources."""
    defaults = dict(
        expert_name="E",
        study=_study([_finding("failure-1", ["sha-a"]), _finding("failure-2", ["sha-b"])]),
        brief=SimpleNamespace(positions=[_position("Does X hold?", ["failure-1", "failure-2"])]),
        corpus_entries=[_entry("sha-a"), _entry("sha-b", "b.org")],
        at="2026-08-09T00:00:00+00:00",
    )
    return build_graph(**{**defaults, **overrides})


class TestTheChainIsCopiedNotInferred:
    def test_findings_point_at_the_sources_their_anchors_were_found_in(self):
        graph = _built()
        anchored = [(e.source, e.target) for e in graph.edges if e.kind == EDGE_ANCHORED_IN]
        assert ("failure-1", "sha-a") in anchored
        assert ("failure-2", "sha-b") in anchored

    def test_positions_point_at_the_findings_they_were_recorded_as_resting_on(self):
        graph = _built()
        rests = [(e.source, e.target) for e in graph.edges if e.kind == EDGE_RESTS_ON]
        assert ("position-1", "failure-1") in rests

    def test_an_anchor_naming_a_source_no_longer_retained_is_not_an_edge(self):
        """A dangling edge would let a claim cite a passage nobody can open."""
        graph = _built(
            study=_study([_finding("failure-1", ["sha-a", "sha-deleted"])]),
            corpus_entries=[_entry("sha-a")],
        )
        assert [e.target for e in graph.edges if e.kind == EDGE_ANCHORED_IN] == ["sha-a"]

    def test_a_position_citing_a_finding_that_does_not_exist_is_not_an_edge(self):
        graph = _built(brief=SimpleNamespace(positions=[_position("Q", ["failure-1", "invented-9"])]))
        assert [e.target for e in graph.edges if e.kind == EDGE_RESTS_ON] == ["failure-1"]


class TestTheIntegrityCheck:
    def test_a_position_resting_on_ungrounded_findings_reaches_no_source(self):
        """Not partially grounded. A bibliography citing empty pages."""
        graph = _built(
            study=_study([_finding("failure-1", [], grounded=False)]),
            brief=SimpleNamespace(positions=[_position("Q", ["failure-1"])]),
        )
        assert not graph.reaches_a_source("position-1")
        assert [p.id for p in graph.unsupported_positions] == ["position-1"]

    def test_one_working_path_is_enough(self):
        graph = _built(
            study=_study([_finding("failure-1", []), _finding("failure-2", ["sha-b"])]),
            brief=SimpleNamespace(positions=[_position("Q", ["failure-1", "failure-2"])]),
            corpus_entries=[_entry("sha-b", "b.org")],
        )
        assert graph.reaches_a_source("position-1")
        assert graph.unsupported_positions == []

    def test_a_position_citing_nothing_reaches_no_source(self):
        graph = _built(brief=SimpleNamespace(positions=[_position("Q", [])]))
        assert graph.unsupported_positions


class TestIsFormed:
    def test_a_traversal_is_required_not_a_node_count(self):
        """A study with no brief has nodes and no path between claim and passage."""
        graph = _built(brief=SimpleNamespace(positions=[]))
        assert graph.findings and graph.sources
        assert not graph.is_formed

    def test_a_complete_chain_is_formed(self):
        assert _built().is_formed

    def test_positions_that_all_dangle_are_not_formed(self):
        graph = _built(
            study=_study([_finding("failure-1", [], grounded=False)]),
            brief=SimpleNamespace(positions=[_position("Q", ["failure-1"])]),
        )
        assert not graph.is_formed

    def test_an_empty_expert_is_not_formed(self):
        assert not build_graph(expert_name="E", study=None, brief=None).is_formed


class TestWhatTheEdgesMakeVisible:
    def test_evidence_no_position_uses_is_surfaced(self):
        graph = _built(
            study=_study([_finding("failure-1", ["sha-a"]), _finding("failure-9", ["sha-b"])]),
            brief=SimpleNamespace(positions=[_position("Q", ["failure-1"])]),
        )
        assert [f.id for f in graph.unused_findings] == ["failure-9"]

    def test_ungrounded_findings_are_not_reported_as_wasted_evidence(self):
        """They are a different problem, and reporting them here buries it."""
        graph = _built(
            study=_study([_finding("failure-1", ["sha-a"]), _finding("failure-9", [], grounded=False)]),
            brief=SimpleNamespace(positions=[_position("Q", ["failure-1"])]),
        )
        assert graph.unused_findings == []

    def test_concentration_is_counted_per_claim_not_per_document(self):
        """Thirty sources where every position routes through two of them."""
        graph = _built(
            study=_study([_finding("f1", ["sha-a"]), _finding("f2", ["sha-a"]), _finding("f3", ["sha-b"])]),
            brief=SimpleNamespace(
                positions=[_position("Q1", ["f1"]), _position("Q2", ["f2"]), _position("Q3", ["f3"])]
            ),
            corpus_entries=[_entry("sha-a", title="Load bearing"), _entry("sha-b", "b.org", title="Minor")],
        )
        assert graph.load_bearing_sources()[0] == ("Load bearing", 2)

    def test_one_position_reaching_a_source_twice_counts_it_once(self):
        graph = _built(
            study=_study([_finding("f1", ["sha-a"]), _finding("f2", ["sha-a"])]),
            brief=SimpleNamespace(positions=[_position("Q", ["f1", "f2"])]),
            corpus_entries=[_entry("sha-a", title="Only")],
        )
        assert graph.load_bearing_sources() == [("Only", 1)]


class TestTemporal:
    def test_findings_carry_the_study_time_they_came_from(self):
        graph = _built()
        assert all(f.first_seen == "2026-08-01T00:00:00+00:00" for f in graph.findings)

    def test_sources_prefer_their_own_retention_time_over_the_build_time(self):
        entry = SimpleNamespace(
            sha256="sha-a", publisher="a.org", origin_key="u", title="t", added_at="2026-01-01T00:00:00+00:00"
        )
        assert _built(corpus_entries=[entry]).sources[0].first_seen == "2026-01-01T00:00:00+00:00"


class TestTheAttributeNameThatBrokeEverything:
    """A CorpusStore entry names its hash `sha256`; findings say `corpus_shas`.

    Reading `sha` produced source nodes with empty ids, dropped every
    anchored_in edge as dangling, and reported a fully supported expert as
    having no position that reaches a source. A wrong attribute name is
    indistinguishable from real corruption in the output, which is what makes
    it worth a test rather than a fix.
    """

    def test_the_store_s_own_attribute_name_is_read(self):
        graph = _built(corpus_entries=[SimpleNamespace(sha256="sha-a", publisher="p", origin_key="u", title="t")])
        assert [n.id for n in graph.sources] == ["sha-a"]
        assert graph.is_formed

    def test_an_entry_with_no_hash_at_all_is_skipped_rather_than_given_an_empty_id(self):
        graph = _built(corpus_entries=[SimpleNamespace(publisher="p", origin_key="u", title="t")])
        assert graph.sources == []


class TestSerialization:
    def test_the_graph_round_trips(self):
        original = _built()
        restored = EvidenceGraph.from_dict(original.to_dict())
        assert restored.stats() == original.stats()
        assert restored.is_formed

    def test_node_attributes_survive_the_round_trip(self):
        restored = EvidenceGraph.from_dict(_built().to_dict())
        assert restored.findings[0].attrs["lens"] == "failure"

    def test_junk_nodes_and_edges_are_dropped_rather_than_raising(self):
        restored = EvidenceGraph.from_dict(
            {"nodes": ["not a dict", {"kind": "source"}], "edges": ["nope", {"from": "a"}]}
        )
        assert restored.nodes == []
        assert restored.edges == []

    def test_the_stats_travel_with_the_payload(self):
        assert _built().to_dict()["stats"]["is_formed"] is True


class TestRender:
    def test_an_unformed_graph_says_so_rather_than_reporting_counts(self):
        text = render_graph(_built(brief=SimpleNamespace(positions=[])))
        assert "pile of nodes" in text

    def test_unsupported_positions_lead_the_document(self):
        graph = _built(
            study=_study([_finding("f1", [], grounded=False)]),
            brief=SimpleNamespace(positions=[_position("Does X hold?", ["f1"])]),
        )
        text = render_graph(graph)
        assert "Positions that reach no source" in text
        assert "Does X hold?" in text

    def test_a_clean_graph_reports_what_the_claims_rest_on(self):
        text = render_graph(_built())
        assert "What the claims actually rest on" in text
        assert "reach no source" not in text
