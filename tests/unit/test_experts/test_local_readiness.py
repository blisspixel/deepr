"""Local capacity refusals stop work and preserve honest evidence."""

import importlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from click.testing import CliRunner

from deepr.backends.capacity import OwnedLocalCapacityRefused
from deepr.backends.local import release_local_model
from deepr.cli.commands.semantic.study_backend import StudyBackend
from deepr.experts import formation
from deepr.experts.chat_backends import ExpertChatRequest
from deepr.experts.investigation.ollama_backend import NativeOllamaInvestigationBackend
from deepr.experts.query_proposal import propose_plan
from deepr.experts.study import run_study
from deepr.experts.study_lenses import resolve_lenses

from .test_formation import environment  # noqa: F401
from .test_study import corpus  # noqa: F401


def _refusing_native_backend():
    return NativeOllamaInvestigationBackend(
        model="fixture",
        get_json=AsyncMock(return_value={"cloud": {"disabled": False, "source": "none"}}),
        post_json=AsyncMock(),
    )


async def _refused_completion(prompt):
    backend = _refusing_native_backend()
    result = await backend.complete(
        ExpertChatRequest(model="fixture", messages=[{"role": "user", "content": prompt}], extra={"num_ctx": 4096})
    )
    return result.text


@pytest.mark.asyncio
async def test_formation_preflights_before_any_research_or_generation(environment, monkeypatch):
    directory, profile, backend = environment
    profile.source_files = [str(directory / "must-not-be-read.txt")]
    backend.preflight = AsyncMock(side_effect=OwnedLocalCapacityRefused("Persistent local capacity proof is missing"))
    release = AsyncMock()
    monkeypatch.setattr("deepr.backends.local.release_local_model", release)

    result = await formation.form_expert(profile, backend)

    assert result["status"] == "incomplete"
    assert result["stage"] == "capacity"
    assert result["model_calls"] == 0
    backend.preflight.assert_awaited_once()
    formation.CostLedger.return_value.record_event.assert_not_called()
    formation.run_search_plan.assert_not_awaited()
    backend.completion.assert_not_awaited()
    release.assert_not_awaited()
    assert not (formation.canonical_expert_dir(profile.name) / "corpus").exists()
    assert (directory / "formation/runs" / result["operation_id"] / "run.json").is_file()
    assert "Persistent local capacity proof is missing" in result["progress"]


@pytest.mark.asyncio
async def test_query_proposal_does_not_hide_native_capacity_refusal():
    with pytest.raises(OwnedLocalCapacityRefused, match=r"cloud\.disabled=true"):
        await propose_plan("Build settings", completion=_refused_completion)


@pytest.mark.asyncio
async def test_study_classifies_native_capacity_refusal_and_stops(corpus):
    completion = AsyncMock(side_effect=_refused_completion)
    checkpoint = []
    result = await run_study(
        expert_name="Example",
        corpus=corpus,
        completion=completion,
        lens_keys=["failure", "contention"],
        checkpoint=lambda value: checkpoint.append(value.to_dict()),
    )

    assert completion.await_count == 1
    assert result.outcomes[0].status == "capacity_refused"
    assert result.exit_code != 0
    assert checkpoint[-1]["outcomes"][0]["status"] == "capacity_refused"


def _partial_completion(corpus):
    chunks = corpus.iter_study_chunks(chunk_chars=160, max_chars=400_000)
    completed_lens_calls = len(chunks)
    calls = 0

    async def complete(prompt):
        nonlocal calls
        calls += 1
        if calls > completed_lens_calls + 1:
            raise OwnedLocalCapacityRefused("Persistent cloud proof changed; generation refused")
        current_chunk = chunks[(calls - 1) % completed_lens_calls]
        field = "fail_patterns" if calls <= completed_lens_calls else "tensions"
        return json.dumps(
            {
                field: [
                    {
                        "name": f"retained-{calls}",
                        "anchors": [current_chunk[0][1][:40]],
                    }
                ]
            }
        )

    return complete, completed_lens_calls


@pytest.mark.asyncio
async def test_refusal_retains_earlier_lens_and_successful_current_chunks(corpus):
    completion, completed_calls = _partial_completion(corpus)
    checkpoints = []
    result = await run_study(
        expert_name="Example",
        corpus=corpus,
        completion=completion,
        lens_keys=["failure", "contention", "mechanism"],
        chunk_chars=160,
        checkpoint=lambda value: checkpoints.append(value.to_dict()),
    )
    assert [outcome.status for outcome in result.outcomes] == ["ok", "capacity_refused"]
    assert len(result.outcomes[0].findings) == completed_calls
    assert len(result.outcomes[1].findings) == 1
    assert result.grounded_findings
    assert result.exit_code == 1
    assert checkpoints[-1]["outcomes"][1]["findings"]
    restored = type(result).from_dict(json.loads(json.dumps(result.to_dict())))
    assert restored.exit_code == 1
    assert len(restored.findings) == completed_calls + 1


def test_standalone_json_study_is_nonzero_and_retains_partial_evidence(corpus, tmp_path, monkeypatch):
    study_cli = importlib.import_module("deepr.cli.commands.semantic.expert_study")
    completion, completed_calls = _partial_completion(corpus)
    backend = StudyBackend(completion, "local:fixture", "$0", chunk_chars=160, model="fixture")
    monkeypatch.setattr(study_cli, "_load_profile", lambda name: SimpleNamespace(name=name))
    monkeypatch.setattr(
        study_cli, "_prepare_study", lambda **kwargs: (resolve_lenses(["failure", "contention"]), corpus, backend)
    )
    monkeypatch.setattr(study_cli, "canonical_study_path", lambda name: tmp_path / "study.json")
    monkeypatch.setattr(study_cli, "_warn_if_cpu_bound", AsyncMock())
    monkeypatch.setattr(study_cli, "_resume_source", lambda *args, **kwargs: [])
    monkeypatch.setattr("deepr.backends.local.release_local_model", AsyncMock())

    result = CliRunner().invoke(study_cli.expert_study, ["Example", "--local", "--json"])
    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["outcomes"][1]["status"] == "capacity_refused"
    assert payload["totals"]["findings"] == completed_calls + 1
    assert json.loads((tmp_path / "study.json").read_text()) == payload


@pytest.mark.asyncio
async def test_refused_lens_is_not_reused_when_capacity_returns(corpus):
    failed = await run_study(
        expert_name="Example",
        corpus=corpus,
        completion=_refused_completion,
        lens_keys=["failure"],
    )
    completion = AsyncMock(
        return_value='{"fail_patterns": [{"name": "recovered", "anchors": ["The reconciler applies desired state"]}]}'
    )
    retried = await run_study(
        expert_name="Example",
        corpus=corpus,
        completion=completion,
        lens_keys=["failure"],
        resume_from=failed.outcomes,
    )
    completion.assert_awaited_once()
    assert retried.outcomes[0].status == "ok"
    assert retried.exit_code == 0


@pytest.mark.asyncio
async def test_native_dispatch_revalidates_after_successful_preflight():
    materialized = {
        "name": "fixture",
        "model": "fixture",
        "size": 100,
        "digest": "a" * 64,
        "details": {"format": "gguf"},
    }
    requests = []

    async def get_json(url, timeout):
        requests.append(url)
        if url.endswith("/api/tags"):
            return {"models": [materialized]}
        return {"cloud": {"disabled": len(requests) == 1, "source": "config"}}

    post = AsyncMock()
    backend = NativeOllamaInvestigationBackend(model="fixture", get_json=get_json, post_json=post)
    await backend.preflight()
    with pytest.raises(OwnedLocalCapacityRefused):
        await backend.complete(ExpertChatRequest(model="fixture", messages=[], extra={"num_ctx": 4096}))
    assert [url.rsplit("/", 1)[1] for url in requests] == ["status", "tags", "status"]
    post.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("refused_dispatch", [1, 2], ids=["query", "study"])
async def test_formation_does_not_unload_after_native_capacity_loss(environment, monkeypatch, refused_dispatch):
    _, profile, _ = environment
    status_reads = 0

    async def get_json(url, timeout):
        nonlocal status_reads
        if url.endswith("/api/status"):
            status_reads += 1
            return {"cloud": {"disabled": status_reads <= refused_dispatch, "source": "config"}}
        return {
            "models": [
                {
                    "name": "fixture",
                    "model": "fixture",
                    "size": 100,
                    "digest": "a" * 64,
                    "details": {"format": "gguf"},
                }
            ]
        }

    chat_post = AsyncMock(return_value={"message": {"content": "local result"}})
    native = NativeOllamaInvestigationBackend(model="fixture", get_json=get_json, post_json=chat_post)

    async def completion(prompt):
        result = await native.complete(
            ExpertChatRequest(model="fixture", messages=[{"role": "user", "content": prompt}], extra={"num_ctx": 4096})
        )
        return result.text

    backend = StudyBackend(
        model="fixture",
        capacity_source="local:fixture",
        cost_note="$0",
        completion=completion,
        preflight=native.preflight,
    )
    cleanup_client = AsyncMock()
    cleanup_client.post.return_value = SimpleNamespace(status_code=200)
    client_factory = Mock(return_value=cleanup_client)
    cleanup_client.__aenter__.return_value = cleanup_client
    monkeypatch.setattr("httpx.AsyncClient", client_factory)
    monkeypatch.setattr("deepr.backends.local.release_local_model", release_local_model)
    monkeypatch.setattr(formation, "propose_plan", propose_plan)

    result = await formation.form_expert(profile, backend)

    assert result["status"] == "incomplete"
    assert result["stage"] == "capacity"
    assert result["error_type"] == "OwnedLocalCapacityRefused"
    assert result["model_calls"] == refused_dispatch
    assert result["calls"][-1]["status"] == "failed"
    assert status_reads == refused_dispatch + 1
    assert chat_post.await_count == refused_dispatch - 1
    assert formation.CostLedger.return_value.record_event.call_count == refused_dispatch
    cleanup_client.post.assert_not_awaited()
    client_factory.assert_not_called()


@pytest.mark.asyncio
async def test_formation_surfaces_late_refusal_without_briefing(environment, monkeypatch):
    _, profile, backend = environment
    from deepr.experts.study_contracts import LensOutcome, StudyResult

    monkeypatch.setattr(
        formation,
        "run_study",
        AsyncMock(
            return_value=StudyResult(
                expert_name=profile.name,
                outcomes=[
                    LensOutcome(
                        lens="synopsis",
                        axis="interrogation",
                        status="capacity_refused",
                        detail="Cloud proof changed; restart daemon",
                    )
                ],
            )
        ),
    )
    brief = AsyncMock()
    monkeypatch.setattr(formation, "build_brief", brief)
    result = await formation.form_expert(profile, backend)
    assert result["status"] == "incomplete"
    assert result["stage"] == "capacity"
    assert "Cloud proof changed" in result["progress"]
    brief.assert_not_awaited()


def test_cli_make_and_build_show_early_capacity_refusal(environment, monkeypatch):
    _, profile, backend = environment
    build_cli = importlib.import_module("deepr.cli.commands.semantic.expert_build")
    local_cli = importlib.import_module("deepr.cli.commands.semantic.local_expert")
    backend.preflight = AsyncMock(side_effect=OwnedLocalCapacityRefused("Persistent proof missing; restart Ollama"))
    monkeypatch.setattr(build_cli, "build_study_backend", lambda **kwargs: backend)
    monkeypatch.setattr(build_cli.ExpertStore, "load", lambda self, name: profile)
    monkeypatch.setattr(local_cli, "create_local_expert_profile", lambda **kwargs: profile)

    built = CliRunner().invoke(build_cli.expert_build, [profile.name, "--local-model", "fixture"])
    assert built.exit_code != 0
    assert "Persistent proof missing; restart Ollama" in built.output
    import click

    with pytest.raises(click.ClickException, match="Persistent proof missing; restart Ollama"):
        local_cli.make_local_expert_profile(
            name=profile.name,
            files=(),
            description="Example",
            local_model="fixture",
            learning_options_used=False,
        )
    backend.completion.assert_not_awaited()
    formation.run_search_plan.assert_not_awaited()


def test_dashboard_worker_retains_early_capacity_refusal(environment, monkeypatch):
    _, profile, backend = environment
    api = importlib.import_module("deepr.web.expert_formation_api")
    backend.preflight = AsyncMock(side_effect=OwnedLocalCapacityRefused("Cloud enabled; set daemon config"))
    monkeypatch.setattr("deepr.cli.commands.semantic.study_backend.build_study_backend", lambda **kwargs: backend)
    targets = []
    monkeypatch.setattr(
        api.threading, "Thread", lambda **kwargs: SimpleNamespace(start=lambda: targets.append(kwargs["target"]))
    )
    assert api.start_formation(profile)
    targets[0]()
    state = formation.read_formation_state(profile.name)
    assert state["status"] == "incomplete"
    assert state["stage"] == "capacity"
    assert state["model_calls"] == 0
    assert "set daemon config" in state["progress"]
    backend.completion.assert_not_awaited()


@pytest.mark.asyncio
async def test_pinned_digest_replacement_is_refused_before_generation():
    entry = {"name": "fixture", "model": "fixture", "size": 1024, "digest": "a" * 64, "details": {"format": "gguf"}}
    get = AsyncMock(
        side_effect=[
            {"cloud": {"disabled": True, "source": "config"}},
            {"models": [entry]},
            {"cloud": {"disabled": True, "source": "config"}},
            {"models": [{**entry, "digest": "b" * 64}]},
        ]
    )
    post = AsyncMock()
    native = NativeOllamaInvestigationBackend(model="fixture", get_json=get, post_json=post)
    await native.preflight()
    native.pinned_digest = native.last_attested_digest
    with pytest.raises(OwnedLocalCapacityRefused, match="changed after preflight"):
        await native.complete(ExpertChatRequest(model="fixture", messages=[], extra={"num_ctx": 4096}))
    post.assert_not_awaited()
