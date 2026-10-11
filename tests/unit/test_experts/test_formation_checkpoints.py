"""Real formation admission, chunk recovery, acquisition and operator limits."""

import asyncio
import json
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from click.testing import CliRunner

from deepr.backends.capacity import OwnedLocalCapacityRefused
from deepr.experts import formation
from deepr.experts.brief_contracts import ExpertBrief, Position
from deepr.experts.study import run_study

from .test_formation import environment  # noqa: F401


@pytest.mark.parametrize("reference", ["../other", "/outside", "A" * 32, "a" * 33, True, [], {}])
@pytest.mark.parametrize("kind", ["checkpoint", "acquisition"])
def test_recovery_references_cannot_follow_malformed_or_external_paths(tmp_path, reference, kind):
    run = SimpleNamespace(directory=tmp_path, previous={f"{kind}_operation_id": reference})
    assert formation._previous_directory(run, kind=kind) is None


@pytest.mark.asyncio
async def test_real_chunked_formation_resumes_at_next_chunk_and_publishes_only_complete(environment, monkeypatch):
    directory, profile, backend = environment
    corpus = formation.CorpusStore(profile.name)
    text = "A compound operation needs coordination. " * 10
    corpus.add(text, origin_key="operator:fixture")
    backend.chunk_chars = 100
    backend.model_contract = lambda: {"model": "fixture", "digest": "a" * 64, "options": {"num_ctx": 16384}}
    prompts = []

    async def complete(prompt):
        prompts.append(prompt)
        match = re.search(r'single top-level key "([^"]+)"', prompt)
        if match:
            return json.dumps({match.group(1): [{"name": "Coordination", "anchors": [text[:35]]}]})
        return "{}"

    async def brief(**kwargs):
        await kwargs["completion"]("Write the brief")
        return ExpertBrief(
            expert_name=profile.name,
            positions=[
                Position(
                    question="Can operations interleave?",
                    stance="Yes",
                    reasoning="Source describes coordination",
                    would_change_my_mind="A transaction guarantee",
                    supported_by=[kwargs["result"].findings[0].finding_id],
                )
            ],
        )

    backend.completion = complete
    monkeypatch.setattr(formation, "run_study", run_study)
    monkeypatch.setattr(formation, "build_brief", brief)
    first = await formation.form_expert(
        profile, backend, discover=False, limits=formation.FormationLimits(max_model_calls=2)
    )
    assert first["status"] == "incomplete"
    assert first["model_calls"] == len(prompts) == 2
    prior = directory / "formation/runs" / first["operation_id"]
    before = (prior / "run.json").read_bytes()
    assert len(list((prior / "study-chunks").glob("synopsis-*.json"))) == 2
    assert not (directory / "hold/current.json").exists()
    second = await formation.form_expert(
        profile, backend, discover=False, limits=formation.FormationLimits(max_elapsed_seconds=21600)
    )
    assert second["status"] == "research_complete", second
    total = len(corpus.iter_study_chunks(chunk_chars=100)) * 3
    assert second["model_calls"] == total - 2 + 1
    assert second["study_progress"]["chunks_reused"] == 2
    assert second["study_progress"]["chunks_completed"] == total
    assert (prior / "run.json").read_bytes() == before
    assert (directory / "hold/current.json").exists()


@pytest.mark.asyncio
async def test_retry_reuses_inspectable_acquisition_without_research_call(environment):
    directory, profile, backend = environment
    first = await formation.form_expert(profile, backend, limits=formation.FormationLimits(max_model_calls=1))
    assert first["status"] == "incomplete"
    prior = directory / "formation/runs" / first["operation_id"]
    assert (prior / "acquisition-manifest.json").exists()
    second = await formation.form_expert(profile, backend, limits=formation.FormationLimits(max_model_calls=2))
    assert second["status"] == "research_complete", second
    assert second["acquisition_reused_from"] == first["operation_id"]
    assert second["model_calls"] == 2
    formation.run_search_plan.assert_awaited_once()
    current = directory / "formation/runs" / second["operation_id"]
    for filename in ("search-plan.json", "search-result.json", "acquisition.json", "acquisition-manifest.json"):
        assert (prior / filename).read_bytes() == (current / filename).read_bytes()


@pytest.mark.parametrize("stop", ["refusal", "cancellation"])
@pytest.mark.asyncio
async def test_retry_chain_preserves_chunks_across_pre_study_stop(environment, monkeypatch, stop):
    directory, profile, backend = environment
    backend.chunk_chars = 100
    backend.model_contract = lambda: {"model": "fixture", "digest": "a" * 64, "options": {"num_ctx": 16384}}
    prompts = []

    async def complete(prompt):
        prompts.append(prompt)
        match = re.search(r'single top-level key "([^"]+)"', prompt)
        return json.dumps({match.group(1): []}) if match else "{}"

    backend.completion = complete
    monkeypatch.setattr(formation, "run_study", run_study)
    # Acquisition consumes one call, then two actual chunks are checkpointed.
    first = await formation.form_expert(profile, backend, limits=formation.FormationLimits(max_model_calls=3))
    assert first["study_progress"]["chunks_completed"] == 2
    prior = directory / "formation/runs" / first["operation_id"]
    before = {path.relative_to(prior): path.read_bytes() for path in prior.rglob("*.json")}
    seen = len(prompts)
    backend.preflight.side_effect = (
        OwnedLocalCapacityRefused("Capacity temporarily unavailable") if stop == "refusal" else asyncio.CancelledError()
    )
    if stop == "cancellation":
        with pytest.raises(asyncio.CancelledError):
            await formation.form_expert(profile, backend)
        middle = formation.read_formation_state(profile.name)
    else:
        middle = await formation.form_expert(profile, backend)
        assert middle["status"] == "incomplete"
    assert middle["model_calls"] == 0
    assert len(prompts) == seen
    assert middle["checkpoint_operation_id"] == first["operation_id"]
    assert middle["acquisition_operation_id"] == first["operation_id"]
    backend.preflight.side_effect = None
    third = await formation.form_expert(profile, backend, limits=formation.FormationLimits(max_model_calls=1))
    assert third["study_progress"]["chunks_reused"] == 2
    assert third["study_progress"]["chunks_completed"] == 3
    assert third["model_calls"] == 1
    assert third["acquisition_reused_from"] == first["operation_id"]
    assert formation.run_search_plan.await_count == 1
    assert prompts[seen] != prompts[1], "the first completed study prompt must not repeat"
    assert {path.relative_to(prior): path.read_bytes() for path in prior.rglob("*.json")} == before


@pytest.mark.parametrize("change", ["mission", "plan", "source", "refresh"])
@pytest.mark.asyncio
async def test_acquisition_reuse_rejects_changed_identity(environment, change):
    directory, profile, backend = environment
    first = await formation.form_expert(profile, backend, limits=formation.FormationLimits(max_model_calls=1))
    prior = directory / "formation/runs" / first["operation_id"]
    if change == "mission":
        profile.description = "Different mission"
    if change == "plan":
        (prior / "search-plan.json").write_text('{"changed": true}')
    if change == "source":
        formation.CorpusStore(profile.name).add("Additional material", origin_key="operator:new")
    second = await formation.form_expert(profile, backend, refresh_sources=change == "refresh")
    assert second["status"] == "research_complete", second
    assert "acquisition_reused_from" not in second
    assert formation.run_search_plan.await_count == 2


@pytest.mark.parametrize("failed_artifact", ["search-plan.json", "acquisition-manifest.json"])
@pytest.mark.asyncio
async def test_acquisition_copy_failure_stops_retry_without_new_dispatch(environment, monkeypatch, failed_artifact):
    directory, profile, backend = environment
    first = await formation.form_expert(profile, backend, limits=formation.FormationLimits(max_model_calls=1))
    prior = directory / "formation/runs" / first["operation_id"]
    previous_bytes = {path.relative_to(prior): path.read_bytes() for path in prior.rglob("*.json")}
    corpus_before = formation.CorpusStore(profile.name).load_study_material()
    backend.completion.reset_mock()
    formation.run_search_plan.reset_mock()
    real_artifact = formation.FormationRun.artifact

    def fail_copy(run, name, payload):
        if name == failed_artifact:
            raise OSError("Synthetic current-acquisition durable-copy failure")
        return real_artifact(run, name, payload)

    monkeypatch.setattr(formation.FormationRun, "artifact", fail_copy)
    second = await formation.form_expert(profile, backend)
    assert second["status"] == "incomplete"
    assert second["error_type"] == "OSError"
    assert second["model_calls"] == 0
    assert second["acquisition_operation_id"] == first["operation_id"]
    backend.completion.assert_not_awaited()
    formation.run_search_plan.assert_not_awaited()
    assert formation.CorpusStore(profile.name).load_study_material() == corpus_before
    assert {path.relative_to(prior): path.read_bytes() for path in prior.rglob("*.json")} == previous_bytes
    assert not (directory / "hold/current.json").exists()


@pytest.mark.parametrize("minutes", [0, -1, 361])
def test_invalid_make_time_is_rejected_before_profile_write(monkeypatch, minutes):
    from deepr.cli.main import cli

    create = Mock()
    monkeypatch.setattr("deepr.cli.commands.semantic.local_expert.create_local_expert_profile", create)
    result = CliRunner().invoke(cli, ["expert", "make", "Bounded", "--local", "--max-minutes", str(minutes)])
    assert result.exit_code != 0
    create.assert_not_called()


@pytest.mark.parametrize("chars", [0, -1, 120001])
def test_invalid_make_corpus_limit_is_rejected_before_profile_write(monkeypatch, chars):
    from deepr.cli.main import cli

    create = Mock()
    monkeypatch.setattr("deepr.cli.commands.semantic.local_expert.create_local_expert_profile", create)
    result = CliRunner().invoke(cli, ["expert", "make", "Bounded", "--local", "--max-corpus-chars", str(chars)])
    assert result.exit_code != 0
    create.assert_not_called()


def test_six_hour_make_and_reduced_corpus_reach_existing_owned_local_limits(monkeypatch):
    from deepr.cli.main import cli

    build = Mock()
    monkeypatch.setenv("DEEPR_LOCAL_MODEL", "fixture")
    monkeypatch.setattr("deepr.cli.commands.semantic.expert_build.build_local_expert", build)
    result = CliRunner().invoke(
        cli, ["expert", "make", "Bounded", "--local", "--max-minutes", "360", "--max-corpus-chars", "20000"]
    )
    assert result.exit_code == 0, result.output
    limits = build.call_args.kwargs["limits"]
    assert limits.max_elapsed_seconds == 21600
    assert limits.max_corpus_chars == 20000
    assert limits.max_model_calls == 40
    assert build.call_args.kwargs["fresh_default"] is True


@pytest.mark.parametrize(
    "explicit,previous,recorded,expected",
    [
        ("explicit", "previous", "recorded", "explicit"),
        (None, "previous", "recorded", "previous"),
        (None, None, "recorded", "recorded"),
        (None, None, "ollama", None),
    ],
)
def test_build_pins_explicit_recorded_or_previous_model(
    environment, monkeypatch, explicit, previous, recorded, expected
):
    from deepr.cli.commands.semantic import expert_build

    _, profile, backend = environment
    profile.model = recorded
    monkeypatch.setattr(expert_build, "read_formation_state", lambda _: {"model": previous})
    builder = Mock(return_value=backend)
    monkeypatch.setattr(expert_build, "build_study_backend", builder)
    monkeypatch.setattr(
        expert_build,
        "form_expert",
        AsyncMock(return_value={"status": "research_complete", "knowledge_index": "knowledge/index.md"}),
    )
    expert_build.build_local_expert(profile, model=explicit)
    assert builder.call_args.kwargs["model"] == expected


@pytest.mark.parametrize("previous,expected", [(None, None), ("selected-before", "selected-before")])
def test_fresh_automatic_profile_preserves_default_selection_until_first_operation(
    environment, monkeypatch, previous, expected
):
    from deepr.cli.commands.semantic import expert_build

    _, profile, backend = environment
    profile.model = "automatic-profile-default"
    monkeypatch.setattr(expert_build, "read_formation_state", lambda _: {"model": previous})
    builder = Mock(return_value=backend)
    monkeypatch.setattr(expert_build, "build_study_backend", builder)
    monkeypatch.setattr(
        expert_build,
        "form_expert",
        AsyncMock(return_value={"status": "research_complete", "knowledge_index": "knowledge/index.md"}),
    )
    expert_build.build_local_expert(profile, fresh_default=True)
    assert builder.call_args.kwargs["model"] == expected
