"""Optional local embedding routing for consult findings (#264)."""

import asyncio

import pytest

from deepr.experts import consult_routing as routing
from deepr.experts.consult_context import gather_findings
from deepr.experts.study_contracts import LensOutcome, StudyFinding, StudyResult


def _finding(fid: str, text: str) -> StudyFinding:
    return StudyFinding(
        lens="synopsis", axis="interrogation", kind="notes", title=text, finding_id=fid, grounded_anchor_count=1
    )


def _study(findings):
    return StudyResult(
        expert_name="E", outcomes=[LensOutcome(lens="synopsis", axis="interrogation", status="ok", findings=findings)]
    )


def _crowded_study():
    """Thirty lexical decoys outrank the one finding phrased differently from the question."""
    decoys = [_finding(f"decoy-{n}", "tern agents idempotency keys default note") for n in range(30)]
    answer = _finding("answer", "Keys are enabled on every agent platform")
    return _study([*decoys, answer])


def test_without_a_ranking_lexical_routing_is_unchanged():
    study = _crowded_study()
    chosen = gather_findings("Tern agents: idempotency keys default?", study, [])
    assert "answer" not in [f.finding_id for f in chosen]
    assert len(chosen) == 24


def test_semantic_ranking_offers_a_crowded_out_finding():
    study = _crowded_study()
    ranking = ["answer", *[f"decoy-{n}" for n in range(30)]]
    chosen = [
        f.finding_id
        for f in gather_findings("Tern agents: idempotency keys default?", study, [], semantic_ranking=ranking)
    ]
    assert "answer" in chosen
    assert len(chosen) == 24


def test_position_support_is_still_carried_first():
    from deepr.experts.brief_contracts import Position

    study = _crowded_study()
    position = Position(question="q", stance="s", reasoning="r", would_change_my_mind="", supported_by=["decoy-29"])
    chosen = [f.finding_id for f in gather_findings("unrelated", study, [position], semantic_ranking=["answer"])]
    assert "decoy-29" in chosen and "answer" in chosen


def test_router_orders_findings_by_cosine_similarity():
    vectors = {"q": (1.0, 0.0), "near": (0.9, 0.1), "far": (0.0, 1.0)}

    async def embed(texts):
        return [vectors[text.split()[0]] for text in texts]

    router = routing.FindingRouter("fixture-embed", embed_query=embed, embed_documents=embed)
    findings = [_finding("f-far", "far"), _finding("f-near", "near"), _finding("", "near unnamed")]
    assert asyncio.run(router.rank("q", findings)) == ["f-near", "f-far"]
    assert asyncio.run(router.rank("  ", findings)) == []
    assert "did not establish relevance" in router.note


def test_routing_is_off_without_configuration(monkeypatch):
    monkeypatch.delenv(routing.CONSULT_EMBEDDING_MODEL_ENV, raising=False)
    assert routing.configured_finding_router() is None
    assert asyncio.run(routing.route_expert_findings(None, "q", "E")) == (None, "")


def test_configuration_builds_a_local_router(monkeypatch):
    monkeypatch.setenv(routing.CONSULT_EMBEDDING_MODEL_ENV, " nomic-embed-text:v1.5 ")
    built = []
    monkeypatch.setattr(routing, "local_finding_router", lambda model: built.append(model) or "router")
    assert routing.configured_finding_router() == "router"
    assert built == ["nomic-embed-text:v1.5"]


def test_router_failure_falls_back_to_lexical_with_a_note(monkeypatch, tmp_path):
    async def broken(texts):
        raise ConnectionError("ollama down")

    router = routing.FindingRouter("fixture-embed", embed_query=broken, embed_documents=broken)
    monkeypatch.setattr("deepr.experts.consult_context.load_study", lambda path: _crowded_study())
    ranking, note = asyncio.run(routing.route_expert_findings(router, "q", "E"))
    assert ranking is None
    assert "unavailable (ConnectionError)" in note and "lexical overlap only" in note


def test_router_without_a_study_stays_silent(monkeypatch):
    async def embed(texts):
        pytest.fail("no study, no embedding call")

    router = routing.FindingRouter("fixture-embed", embed_query=embed, embed_documents=embed)
    monkeypatch.setattr("deepr.experts.consult_context.load_study", lambda path: None)
    assert asyncio.run(routing.route_expert_findings(router, "q", "E")) == (None, "")


def test_council_passes_the_ranking_and_its_disclosure_to_the_packet(monkeypatch):
    from deepr.experts.council import ExpertCouncil, ExpertPerspective

    async def fake_route(router, question, name):
        assert router == "router"
        return ["answer"], "routing note"

    seen = {}

    def fake_load(self, query, name, domain, semantic_ranking=None, routing_note=""):
        seen.update(ranking=semantic_ranking, note=routing_note)
        return ExpertPerspective(expert_name=name, domain=domain, response="packet", context={})

    monkeypatch.setattr(routing, "route_expert_findings", fake_route)
    monkeypatch.setattr(ExpertCouncil, "_load_stored_perspective", fake_load)
    council = ExpertCouncil(synthesis_provider="local", finding_router="router")
    perspective = asyncio.run(council._query_expert("q", {"name": "E"}, 0.0, None, None))
    assert perspective.response == "packet"
    assert seen == {"ranking": ["answer"], "note": "routing note"}


def test_consult_context_discloses_the_routing(tmp_path):
    from deepr.experts.consult_context import build_consult_context

    context = build_consult_context(
        expert_name="E",
        question="Tern agents keys?",
        brief=None,
        result=_crowded_study(),
        corpus=None,
        semantic_ranking=["answer"],
        routing_note="Findings were offered by lexical overlap fused with local embedding similarity (m).",
    )
    assert "answer" in [f.finding_id for f in context.findings]
    assert any("local embedding similarity" in item for item in context.limitations)


def test_config_key_maps_to_the_routing_environment_name():
    from deepr.cli.commands.config import _normalize_config_key_value

    assert _normalize_config_key_value("consult.embedding_model", " nomic-embed-text:v1.5 ") == (
        routing.CONSULT_EMBEDDING_MODEL_ENV,
        "nomic-embed-text:v1.5",
    )
