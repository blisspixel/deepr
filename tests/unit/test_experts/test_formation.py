"""Formation produces inspectable research, not a manufactured expertise label."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from deepr.experts import formation
from deepr.experts.acquisition_plan import AcquisitionPlan, AcquisitionQuery
from deepr.experts.brief_contracts import ExpertBrief, Position
from deepr.experts.corpus_search import SearchHit, SearchResult
from deepr.experts.study_contracts import LensOutcome, StudyFinding, StudyResult


@pytest.fixture
def environment(tmp_path, monkeypatch):
    monkeypatch.setattr("deepr.experts.paths.canonical_expert_dir", lambda name: tmp_path)
    monkeypatch.setattr(formation, "canonical_expert_dir", lambda name: tmp_path)
    monkeypatch.setattr(formation, "CostLedger", Mock())
    profile = SimpleNamespace(name="Example", domain="Coordination", description="Coordination")
    backend = SimpleNamespace(
        model="fixture",
        capacity_source="local:fixture",
        chunk_chars=14000,
        completion=AsyncMock(return_value="local result"),
    )

    async def plan(topic, completion):
        await completion("Plan source acquisition")
        return AcquisitionPlan(topic=topic, queries=[AcquisitionQuery("reference", "primary", "original material")])

    async def study(**kwargs):
        await kwargs["completion"]("Read the source")
        entry = kwargs["corpus"].active_entries()[0]
        finding = StudyFinding(
            lens="mechanism",
            axis="interrogation",
            kind="concepts",
            title="Coordination",
            finding_id="f1",
            corpus_shas=[entry.sha256],
            grounded_anchor_count=1,
        )
        return StudyResult(
            expert_name="Example",
            started_at="2026-09-20T12:00:00Z",
            outcomes=[
                LensOutcome(
                    lens=lens,
                    axis="interrogation",
                    status="ok",
                    findings=[finding] if lens == "mechanism" else [],
                    corpus_fingerprint="actual-fixture-corpus",
                )
                for lens in ("synopsis", "mechanism", "failure")
            ],
        )

    async def brief(**kwargs):
        await kwargs["completion"]("Form a position")
        return ExpertBrief(
            expert_name="Example",
            positions=[
                Position(
                    question="Can these operations interleave?",
                    stance="Yes.",
                    reasoning="They execute independently.",
                    would_change_my_mind="A documented transaction guarantee.",
                    supported_by=["f1"],
                )
            ],
        )

    fetch = AsyncMock(
        return_value=SimpleNamespace(
            text="A compound operation needs coordination. " * 10, title="Coordination reference", status_code=200
        )
    )
    monkeypatch.setattr(formation, "propose_plan", plan)
    monkeypatch.setattr(
        formation,
        "run_search_plan",
        AsyncMock(
            return_value=SearchResult(
                hits=[SearchHit(url="https://docs.example/coordination", query="reference", arm="primary")], answered=1
            )
        ),
    )
    monkeypatch.setattr(formation, "default_fetch_page", lambda: fetch)
    monkeypatch.setattr(formation, "run_study", study)
    monkeypatch.setattr(formation, "build_brief", brief)
    monkeypatch.setattr("deepr.backends.local.release_local_model", AsyncMock(return_value=True))
    return tmp_path, profile, backend


@pytest.mark.asyncio
async def test_formation_connects_acquisition_understanding_graph_and_markdown(environment):
    directory, profile, backend = environment
    result = await formation.form_expert(profile, backend)
    assert result["status"] == "research_complete", result
    assert result["qualification"] == "not_reviewed"
    assert result["api_cost_usd"] == 0
    assert result["model_calls"] == backend.completion.await_count == 3
    assert formation.CostLedger.return_value.record_event.call_count == 3
    assert (directory / result["knowledge_index"]).is_file()
    assert json.loads((directory / "graph/evidence.json").read_text())["stats"]["is_formed"]
    assert (directory / "hold/current.md").is_file()
    assert (directory / "formation/runs" / result["operation_id"] / "review.md").is_file()


@pytest.mark.asyncio
async def test_empty_search_does_not_create_fake_understanding(environment, monkeypatch):
    directory, profile, backend = environment
    monkeypatch.setattr(formation, "run_search_plan", AsyncMock(return_value=SearchResult()))
    result = await formation.form_expert(profile, backend)
    assert result["status"] == "incomplete"
    assert "No source material" in result["progress"]
    assert not (directory / "hold/current.json").exists()
    assert backend.completion.await_count == 1


@pytest.mark.asyncio
async def test_call_limit_stops_dispatch_and_keeps_candidate_evidence(environment):
    directory, profile, backend = environment
    result = await formation.form_expert(profile, backend, limits=formation.FormationLimits(max_model_calls=2))
    assert result["status"] == "incomplete"
    assert backend.completion.await_count == 2
    assert (directory / "formation/runs" / result["operation_id"] / "study.json").exists()
    assert not (directory / "hold/current.json").exists()


@pytest.mark.asyncio
async def test_existing_formed_expert_is_never_overwritten(environment):
    directory, profile, backend = environment
    path = directory / "hold/current.json"
    path.parent.mkdir()
    path.write_text("Existing knowledge", encoding="utf-8")
    with pytest.raises(ValueError, match="already has a brief"):
        await formation.form_expert(profile, backend)
    assert path.read_text() == "Existing knowledge"
    backend.completion.assert_not_awaited()


@pytest.mark.asyncio
async def test_concurrent_change_blocks_promotion(environment, monkeypatch):
    directory, profile, backend = environment
    original = formation.build_brief

    async def concurrent(**kwargs):
        result = await original(**kwargs)
        (directory / "noticed").mkdir()
        (directory / "noticed/current.json").write_text("Concurrent study", encoding="utf-8")
        return result

    monkeypatch.setattr(formation, "build_brief", concurrent)
    result = await formation.form_expert(profile, backend)
    assert result["status"] == "incomplete"
    assert "state changed" in result["progress"]
    assert (directory / "noticed/current.json").read_text() == "Concurrent study"
    assert not (directory / "hold/current.json").exists()


@pytest.mark.asyncio
async def test_cancellation_has_durable_interrupted_outcome(environment):
    directory, profile, backend = environment
    backend.completion.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await formation.form_expert(profile, backend)
    result = json.loads((directory / "formation/current.json").read_text())
    assert result["status"] == "interrupted"
    assert result["calls"][0]["status"] == "interrupted"
    assert not (directory / "hold/current.json").exists()


@pytest.mark.asyncio
async def test_paid_capacity_cannot_enter_formation(environment):
    _, profile, backend = environment
    backend.capacity_source = "api:metered"
    with pytest.raises(ValueError, match="owned local"):
        await formation.form_expert(profile, backend)
    backend.completion.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_offers_completed_candidate_lenses_and_preserves_failed_attempt(environment, monkeypatch):
    directory, profile, backend = environment
    first = await formation.form_expert(profile, backend, limits=formation.FormationLimits(max_model_calls=2))
    original = formation.run_study
    resumed = []

    async def capture(**kwargs):
        resumed.extend(kwargs["resume_from"])
        return await original(**kwargs)

    monkeypatch.setattr(formation, "run_study", capture)
    second = await formation.form_expert(profile, backend, discover=False)
    assert second["status"] == "research_complete"
    assert second["resume_candidate"] == first["operation_id"]
    assert len(resumed) == 3
    prior = json.loads((directory / "formation/runs" / first["operation_id"] / "run.json").read_text())
    assert prior["status"] == "incomplete"


@pytest.mark.asyncio
async def test_seed_only_build_does_not_search(environment, monkeypatch):
    directory, profile, backend = environment
    seed = directory / "seed.md"
    seed.write_text("A retained mechanism with explicit boundaries.", encoding="utf-8")
    profile.source_files = [str(seed)]
    acquisition = AsyncMock(side_effect=AssertionError("Discovery must remain disabled"))
    monkeypatch.setattr(formation, "_acquire", acquisition)
    result = await formation.form_expert(profile, backend, discover=False)
    assert result["status"] == "research_complete"
    assert backend.completion.await_count == 2
    acquisition.assert_not_awaited()


@pytest.mark.asyncio
async def test_authored_notebook_prevents_publication(environment):
    directory, profile, backend = environment
    notebook = directory / "notebook.md"
    notebook.write_text("My authored research", encoding="utf-8")
    result = await formation.form_expert(profile, backend)
    assert result["status"] == "incomplete"
    assert "authored notebook" in result["progress"]
    assert notebook.read_text() == "My authored research"
    assert not (directory / "hold/current.json").exists()


@pytest.mark.asyncio
async def test_elapsed_limit_is_terminal_and_explicit(environment):
    _, profile, backend = environment

    async def slow(prompt):
        await asyncio.sleep(3)

    backend.completion.side_effect = slow
    result = await formation.form_expert(profile, backend, limits=formation.FormationLimits(max_elapsed_seconds=1))
    assert result["status"] == "incomplete"
    assert result["progress"] == "Formation elapsed-time limit exhausted"
    assert backend.completion.await_count == 1


def test_expired_running_state_is_read_as_interrupted_without_rewriting(environment):
    directory, profile, _ = environment
    path = directory / "formation/current.json"
    path.parent.mkdir()
    raw = json.dumps(
        {
            "schema_version": "deepr-formation-v1",
            "status": "running",
            "created_at": "2000-01-01T00:00:00Z",
            "limits": {"max_elapsed_seconds": 1},
        }
    )
    path.write_text(raw, encoding="utf-8")
    assert formation.read_formation_state(profile.name)["status"] == "interrupted"
    assert path.read_text() == raw


@pytest.mark.asyncio
async def test_invalid_brief_leaves_candidate_and_no_consultable_knowledge(environment, monkeypatch):
    directory, profile, backend = environment
    monkeypatch.setattr(formation, "build_brief", AsyncMock(return_value=ExpertBrief(expert_name=profile.name)))
    result = await formation.form_expert(profile, backend)
    assert result["status"] == "incomplete"
    assert (directory / "formation/runs" / result["operation_id"] / "brief.json").is_file()
    assert not (directory / "hold/current.json").exists()
