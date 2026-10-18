"""One selected local profile keeps its model across CLI, MCP and A2A."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from deepr.a2a.consult_tasks import run_consult_task
from deepr.cli.commands.semantic.expert_consult import expert_consult
from deepr.experts.profile import ExpertProfile, ExpertStore
from deepr.mcp.consult_tool import consult_experts_tool


@pytest.fixture
def local_profiles(monkeypatch, tmp_path):
    monkeypatch.setenv("DEEPR_EXPERTS_PATH", str(tmp_path / "experts"))
    monkeypatch.setenv("DEEPR_CONSULT_TRACE_PATH", str(tmp_path / "consult.jsonl"))
    monkeypatch.setenv("DEEPR_LOCAL_MODEL", "global-env:8b")
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    store = ExpertStore()
    profile = ExpertProfile(name="Risk Expert", vector_store_id="local", provider="local", model="profile:32b")
    store.save(profile)
    path = store.find_existing_dir(profile.name) / "profile.json"
    data = json.loads(path.read_text())
    data["schema_version"] = 1
    path.write_text(json.dumps(data))
    path.with_suffix(".json.lock").unlink()
    before = path.read_bytes()
    calls = []

    async def consult(*_args, **kwargs):
        calls.append(kwargs["synthesis_model"])
        return {
            "perspectives": [{"expert_name": "Risk Expert", "response": "stored context", "confidence": 0.8}],
            "synthesis": "bounded answer",
            "total_cost": 0.0,
        }

    monkeypatch.setattr("deepr.backends.local.ollama_chat_client", lambda: object())
    monkeypatch.setattr("deepr.experts.consult.run_consult", consult)
    monkeypatch.setattr("deepr.cli.commands.semantic.expert_consult.run_consult", consult)
    return path, before, calls


async def invoke(interface, experts, model=None):
    if interface == "cli":
        args = ["q", "--json"]
        for expert in experts:
            args.extend(["--expert", expert])
        if model:
            args.extend(["--local-model", model])
        result = await asyncio.to_thread(CliRunner().invoke, expert_consult, args)
        assert result.exit_code == 0, result.output
        return json.loads(result.output)
    if interface == "mcp":
        return await consult_experts_tool(question="q", experts=experts, local_model=model)
    result = await run_consult_task(
        SimpleNamespace(input="q", budget=0.0, metadata={"experts": experts, "local_model": model or ""})
    )
    assert result.ok, result.error
    return result.artifacts[0]["content"]


@pytest.mark.parametrize("interface", ["cli", "mcp", "a2a"])
@pytest.mark.parametrize("name", ["Risk Expert", "RISK EXPERT", "risk_expert"])
async def test_single_profile_model_wins_real_environment_without_migration(local_profiles, interface, name):
    path, before, calls = local_profiles
    payload = await invoke(interface, [name])
    assert calls == ["profile:32b"]
    assert payload["capacity"]["model"] == "profile:32b"
    assert "profile" in payload["capacity"]["model_selection"]
    assert path.read_bytes() == before
    assert not path.with_suffix(".json.lock").exists()


@pytest.mark.parametrize("interface", ["cli", "mcp", "a2a"])
async def test_operation_model_wins_profile_and_environment(local_profiles, interface):
    path, before, calls = local_profiles
    await invoke(interface, ["Risk Expert"], "operation:70b")
    assert calls == ["operation:70b"]
    assert path.read_bytes() == before


@pytest.mark.parametrize("provider,model", [("local", "ollama"), ("openai", "remote-profile")])
async def test_placeholder_and_nonlocal_profile_keep_environment(local_profiles, provider, model):
    path, _, calls = local_profiles
    data = json.loads(path.read_text())
    data.update(provider=provider, model=model)
    path.write_text(json.dumps(data))
    await invoke("mcp", ["Risk Expert"])
    assert calls == ["global-env:8b"]


@pytest.mark.parametrize("experts", [[], ["Risk Expert", "Other Expert"]])
async def test_automatic_and_mixed_councils_keep_global_model(local_profiles, experts):
    _, _, calls = local_profiles
    await invoke("mcp", experts)
    assert calls == ["global-env:8b"]


async def test_inventory_discovery_is_cancelled_inside_consult_deadline(local_profiles, monkeypatch):
    path, _, calls = local_profiles
    data = json.loads(path.read_text())
    data["model"] = "ollama"
    path.write_text(json.dumps(data))
    monkeypatch.delenv("DEEPR_LOCAL_MODEL")
    cancelled = asyncio.Event()

    async def blocked_inventory():
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr("deepr.backends.local.default_local_model_async", blocked_inventory)
    monkeypatch.setattr(
        "deepr.backends.local.default_local_model", lambda: pytest.fail("cannot run sync discovery after cancellation")
    )
    result = await consult_experts_tool(question="q", experts=["Risk Expert"], max_elapsed_seconds=0.1)
    assert result["error_code"] == "CONSULT_ELAPSED_LIMIT"
    assert cancelled.is_set()
    assert calls == []


async def test_unavailable_profile_model_is_not_replaced_by_environment(local_profiles, monkeypatch):
    from deepr.experts.consult import ConsultBackendError

    _, _, calls = local_profiles
    monkeypatch.setattr(
        "deepr.backends.local.default_local_model_async",
        lambda: pytest.fail("pinned model cannot discover a replacement"),
    )

    async def refuse(*_args, **kwargs):
        calls.append(kwargs["synthesis_model"])
        raise ConsultBackendError("Pinned profile model is unavailable; install it or explicitly choose another model.")

    monkeypatch.setattr("deepr.experts.consult.run_consult", refuse)
    result = await consult_experts_tool(question="q", experts=["Risk Expert"])
    assert result["error_code"] == "CONSULT_BACKEND_UNAVAILABLE"
    assert calls == ["profile:32b"]


@pytest.mark.parametrize("interface", ["cli", "mcp", "a2a"])
async def test_completed_formation_model_wins_failed_profile_without_writes(local_profiles, interface):
    from deepr.experts.formation import _snapshot

    path, before, calls = local_profiles
    directory = path.parent
    (directory / "formation").mkdir()
    (directory / "study.json").write_text('{"model": "formed:27b"}')
    (directory / "brief.json").write_text('{"positions": [{"stance": "Retained view"}]}')
    (directory / "positions.json").write_text('{"revisions": []}')
    state = {
        "schema_version": "deepr-formation-v1",
        "status": "research_complete",
        "model": "formed:27b",
        "capacity_source": "local:formed:27b",
        "final_artifacts": _snapshot(directory),
    }
    (directory / "formation/current.json").write_text(json.dumps(state))
    payload = await invoke(interface, ["Risk Expert"])
    assert calls == ["formed:27b"]
    assert payload["capacity"]["model_selection"] == "completed local formation: Risk Expert"
    assert path.read_bytes() == before
    await invoke(interface, ["Risk Expert"], " ")
    assert calls[-1] == "formed:27b"
    await invoke(interface, ["Risk Expert"], "explicit:8b")
    assert calls[-1] == "explicit:8b"
    (directory / "brief.json").write_text('{"positions": [{"stance": "Later view"}]}')
    await invoke(interface, ["Risk Expert"])
    assert calls[-1] == "profile:32b"
