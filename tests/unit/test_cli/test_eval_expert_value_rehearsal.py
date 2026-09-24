"""CLI for the local four-arm rehearsal: plan, run, blind and bind labels."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from deepr.cli.commands import eval_expert_value_rehearsal as cli
from deepr.cli.main import cli as root_cli
from deepr.evals import expert_value_rehearsal as rehearsal
from tests.unit.test_eval.test_expert_value_rehearsal import FakeLauncher, make_plan, make_policy
from tests.unit.test_eval.test_expert_value_sources import Bundle


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    bundle = Bundle(tmp_path / "organizer")
    policy = tmp_path / "policy.json"
    policy.write_text(make_policy().model_dump_json(), encoding="utf-8")
    plan = tmp_path / "plan.json"
    plan.write_text(make_plan().model_dump_json(), encoding="utf-8")
    blueprint = tmp_path / "blueprint.json"
    blueprint.write_text(
        json.dumps(
            {"acceptance_cases": [{"id": c, "question": f"{c}?", "success_criteria": ["s"]} for c in ("c1", "c2")]}
        ),
        encoding="utf-8",
    )
    placement = tmp_path / "placement.json"
    placement.write_text(
        json.dumps(
            {
                "cases": [
                    {"acceptance_case_id": "c1", "source_world_id": "world-1"},
                    {"acceptance_case_id": "c2", "source_world_id": "world-2"},
                ]
            }
        ),
        encoding="utf-8",
    )

    class FakeRun(rehearsal.RehearsalRun):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs, launcher=FakeLauncher())

    monkeypatch.setattr(cli, "RehearsalRun", FakeRun)
    monkeypatch.setattr(cli, "runtime_preflight", lambda _policy: {"ollama_version": "fixture"})
    return {
        "root": tmp_path,
        "index": bundle.index_path,
        "artifacts": bundle.root,
        "policy": policy,
        "plan": plan,
        "blueprint": blueprint,
        "placement": placement,
    }


def invoke(*args: str) -> Any:
    return CliRunner().invoke(root_cli, ["eval", "expert-value-rehearsal", *args])


def test_plan_run_blind_and_bind_end_to_end(workspace: dict[str, Path]) -> None:
    w = workspace
    result = invoke(
        "plan",
        "--blueprint",
        str(w["blueprint"]),
        "--placement",
        str(w["placement"]),
        "--output",
        str(w["root"] / "p.json"),
    )
    assert result.exit_code == 0, result.output
    assert "2 question-only case(s)" in result.output
    run_root = w["root"] / "run"
    common = ["--from-file", str(w["index"]), "--artifact-root", str(w["artifacts"])]
    result = invoke(
        "run", "--policy", str(w["policy"]), "--plan", str(w["plan"]), *common, "--run-root", str(run_root), "--json"
    )
    assert result.exit_code == 0, result.output
    summary = json.loads(result.output)
    assert summary["terminal_cells"] == 8 and summary["api_cost_usd"] == 0
    assert json.loads((run_root / "run.json").read_text())["runtime"] == {"ollama_version": "fixture"}
    packet, key = w["root"] / "review" / "packet.json", w["root"] / "private" / "key.json"
    result = invoke(
        "blind",
        "--run-root",
        str(run_root),
        "--blueprint",
        str(w["blueprint"]),
        "--placement",
        str(w["placement"]),
        *common,
        "--packet-out",
        str(packet),
        "--key-out",
        str(key),
    )
    assert result.exit_code == 0, result.output
    assert "8 blinded answer(s)" in result.output
    entries = json.loads(key.read_text())["entries"]
    labels = w["root"] / "labels.json"
    labels.write_text(
        json.dumps({"reviewer": {"id": "r1"}, "labels": [{"opaque_id": e["opaque_id"], "score": 2} for e in entries]})
    )
    output = w["root"] / "bound.json"
    result = invoke(
        "bind-labels",
        "--run-root",
        str(run_root),
        "--key",
        str(key),
        "--packet",
        str(packet),
        "--labels",
        str(labels),
        "--output",
        str(output),
    )
    assert result.exit_code == 0, result.output
    assert json.loads(output.read_text())["status"] == "labels_bound"
    result = invoke(
        "bind-labels",
        "--run-root",
        str(run_root),
        "--key",
        str(key),
        "--packet",
        str(packet),
        "--labels",
        str(labels),
        "--output",
        str(output),
    )
    assert result.exit_code != 0 and "Refusing to overwrite" in result.output


def test_run_refuses_before_execution(workspace: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    w = workspace

    def mismatch(_policy: Any) -> dict[str, Any]:
        raise ValueError("installed local model digest differs from the frozen policy")

    monkeypatch.setattr(cli, "runtime_preflight", mismatch)
    result = invoke(
        "run",
        "--policy",
        str(w["policy"]),
        "--plan",
        str(w["plan"]),
        "--from-file",
        str(w["index"]),
        "--artifact-root",
        str(w["artifacts"]),
        "--run-root",
        str(w["root"] / "run"),
    )
    assert result.exit_code != 0 and "digest differs" in result.output
    assert not (w["root"] / "run").exists()


def test_run_human_summary_and_invalid_inputs(workspace: dict[str, Path]) -> None:
    w = workspace
    args = ["--from-file", str(w["index"]), "--artifact-root", str(w["artifacts"])]
    result = invoke(
        "run", "--policy", str(w["policy"]), "--plan", str(w["plan"]), *args, "--run-root", str(w["root"] / "run")
    )
    assert result.exit_code == 0 and "unreviewed" in result.output
    bad = w["root"] / "bad-plan.json"
    bad.write_text("{}", encoding="utf-8")
    result = invoke(
        "run", "--policy", str(w["policy"]), "--plan", str(bad), *args, "--run-root", str(w["root"] / "run2")
    )
    assert result.exit_code != 0 and "refused before execution" in result.output
    result = invoke(
        "plan", "--blueprint", str(bad), "--placement", str(w["placement"]), "--output", str(w["root"] / "x.json")
    )
    assert result.exit_code != 0 and "Invalid blueprint" in result.output
    broken = w["root"] / "broken.json"
    broken.write_text("{", encoding="utf-8")
    result = invoke(
        "plan", "--blueprint", str(broken), "--placement", str(w["placement"]), "--output", str(w["root"] / "y.json")
    )
    assert result.exit_code != 0 and "Could not read" in result.output


def test_blind_keeps_key_apart_and_reports_refusals(workspace: dict[str, Path]) -> None:
    w = workspace
    common = ["--from-file", str(w["index"]), "--artifact-root", str(w["artifacts"])]
    same = w["root"] / "same"
    result = invoke(
        "blind",
        "--run-root",
        str(w["root"]),
        "--blueprint",
        str(w["blueprint"]),
        "--placement",
        str(w["placement"]),
        *common,
        "--packet-out",
        str(same / "p.json"),
        "--key-out",
        str(same / "k.json"),
    )
    assert result.exit_code != 0 and "different directory" in result.output
    (w["root"] / "empty" / "cells").mkdir(parents=True)
    result = invoke(
        "blind",
        "--run-root",
        str(w["root"] / "empty"),
        "--blueprint",
        str(w["blueprint"]),
        "--placement",
        str(w["placement"]),
        *common,
        "--packet-out",
        str(w["root"] / "a" / "p.json"),
        "--key-out",
        str(w["root"] / "b" / "k.json"),
    )
    assert result.exit_code != 0 and "Blinding refused" in result.output
    key = w["root"] / "k.json"
    key.write_text("{}", encoding="utf-8")
    result = invoke(
        "bind-labels",
        "--run-root",
        str(w["root"]),
        "--key",
        str(key),
        "--packet",
        str(key),
        "--labels",
        str(key),
        "--output",
        str(w["root"] / "o.json"),
    )
    assert result.exit_code != 0 and "Label binding refused" in result.output


def test_real_worker_subprocess_rejects_unknown_phase_without_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise the actual interpreter, module entry point and scrubbed environment."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "must-not-leak")
    policy = make_policy()
    out = tmp_path / "out"
    out.mkdir()
    spec = tmp_path / "spec.json"
    spec.write_text(
        json.dumps(
            {"run_id": "r", "worker_id": "w", "phase": "judge", "output_dir": str(out), "policy": policy.model_dump()}
        )
    )
    env = rehearsal.worker_environment(tmp_path, policy)
    code = rehearsal.subprocess_launcher(spec, env, tmp_path, timeout=120)
    result = json.loads((out / "result.json").read_text())
    assert code == 1
    assert result["status"] == "failed" and result["error"] == "unknown rehearsal phase"
    assert result["model_calls"] == 0


def test_runtime_preflight_binds_digest_and_cloud_status(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = {
        "/api/version": {"version": "0.34.3"},
        "/api/status": {"cloud": {"disabled": True, "source": "both"}},
        "/api/tags": {"models": [{"name": "fixture:14b", "digest": "a" * 64}]},
    }

    class Client:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def __enter__(self) -> Client:
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def get(self, url: str) -> Any:
            payload = responses[url.split("11434")[1]]
            return type("R", (), {"json": lambda _self: payload})()

    import httpx

    monkeypatch.setattr(httpx, "Client", Client)
    runtime = rehearsal.runtime_preflight(make_policy())
    assert runtime["ollama_version"] == "0.34.3"
    responses["/api/tags"] = {"models": [{"name": "fixture:14b", "digest": "c" * 64}]}
    with pytest.raises(ValueError, match="digest differs"):
        rehearsal.runtime_preflight(make_policy())
    responses["/api/status"] = {"cloud": {"disabled": False, "source": "config"}}
    with pytest.raises(ValueError):
        rehearsal.runtime_preflight(make_policy())


def test_subprocess_timeout_is_terminal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    def slow(*_args: Any, **_kwargs: Any) -> Any:
        raise subprocess.TimeoutExpired(cmd="worker", timeout=1)

    monkeypatch.setattr(subprocess, "run", slow)
    assert rehearsal.subprocess_launcher(tmp_path / "spec.json", {}, tmp_path, timeout=1) == -1
