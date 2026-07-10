"""Regression tests for web benchmark and destructive demo action safety."""

from __future__ import annotations

import io
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("flask")

from deepr.web import action_safety
from deepr.web import app as web_app


@pytest.fixture
def client():
    web_app.app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
    if web_app.limiter is not None:
        web_app.limiter.enabled = False
    web_app._benchmark_estimate_cache.clear()
    web_app._benchmark_proc.clear()
    with web_app.app.test_client() as test_client:
        yield test_client
    web_app._benchmark_estimate_cache.clear()
    web_app._benchmark_proc.clear()


def test_benchmark_estimate_runs_repository_script_and_rejects_failure(client, monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout="DEEPR_BENCHMARK_ESTIMATE_JSON="
            + json.dumps({"estimated_cost": 1.25, "model_count": 2, "provider_count": 1}),
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    response = client.post(
        "/api/benchmarks/estimate",
        json={"tier": "research", "quick": True, "no_judge": False},
    )

    assert response.status_code == 200
    assert response.get_json()["estimated_cost"] == 1.25
    command, kwargs = calls[0]
    assert Path(command[1]) == Path(action_safety.benchmark_project_root()) / "scripts" / "benchmark_models.py"
    assert Path(kwargs["cwd"]) == Path(action_safety.benchmark_project_root())

    web_app._benchmark_estimate_cache.clear()
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=2, stdout="", stderr="private failure"),
    )
    failed = client.post("/api/benchmarks/estimate", json={"tier": "chat"})
    assert failed.status_code == 502
    assert failed.get_json() == {"error": "Benchmark estimation failed"}

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout="dry run format changed"),
    )
    malformed = client.post("/api/benchmarks/estimate", json={"tier": "chat"})
    assert malformed.status_code == 502


def test_benchmark_start_enforces_approved_cost_and_repository_script(client, monkeypatch):
    calls = []

    class FakeProcess:
        pid = 123
        stdout = io.StringIO("")

        def poll(self):
            return None

    def fake_popen(command, **kwargs):
        calls.append((command, kwargs))
        return FakeProcess()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    missing = client.post("/api/benchmarks/start", json={"tier": "chat"})
    assert missing.status_code == 400
    assert missing.get_json() == {"error": action_safety.BENCHMARK_COST_VALIDATION_ERROR}
    assert calls == []

    response = client.post(
        "/api/benchmarks/start",
        json={"tier": "research", "quick": True, "no_judge": True, "max_estimated_cost": 1.25},
    )
    assert response.status_code == 200
    command, kwargs = calls[0]
    assert Path(command[1]) == Path(action_safety.benchmark_project_root()) / "scripts" / "benchmark_models.py"
    assert "--quick" in command
    assert "--no-judge" in command
    assert command[command.index("--budget") + 1] == "1.25"
    assert command[command.index("--max-estimated-cost") + 1] == "1.25"
    assert Path(kwargs["cwd"]) == Path(action_safety.benchmark_project_root())


def test_benchmark_start_never_exposes_validation_exception(client, monkeypatch):
    def reject_with_sensitive_exception(_tier, _value):
        raise ValueError("password=hunter2")

    monkeypatch.setattr(action_safety, "approved_benchmark_command", reject_with_sensitive_exception)

    response = client.post(
        "/api/benchmarks/start",
        json={"tier": "chat", "max_estimated_cost": "password=hunter2"},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": action_safety.BENCHMARK_COST_VALIDATION_ERROR}
    assert "hunter2" not in response.get_data(as_text=True)


def test_real_benchmark_dry_run_emits_exact_json_without_provider_calls():
    environment = os.environ.copy()
    for variable in ("OPENAI_API_KEY", "XAI_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "AZURE_PROJECT_ENDPOINT"):
        environment[variable] = ""
    environment["OPENAI_API_KEY"] = "test-key-not-used"
    command = action_safety.benchmark_command(
        "--dry-run", "--format", "json", "--skip-discovery-check", "--tier", "chat", "--quick", "--no-judge"
    )

    result = subprocess.run(
        command,
        cwd=action_safety.benchmark_project_root(),
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(
        next(
            line.removeprefix("DEEPR_BENCHMARK_ESTIMATE_JSON=")
            for line in result.stdout.splitlines()
            if line.startswith("DEEPR_BENCHMARK_ESTIMATE_JSON=")
        )
    )
    assert payload["estimated_cost"] >= 0
    assert payload["model_count"] > 0
    assert payload["provider_count"] == 1


@pytest.mark.parametrize("value", [None, True, -0.01, float("inf"), "not-a-number"])
def test_benchmark_cost_rejects_invalid_approval(value):
    with pytest.raises(ValueError, match="non-negative number"):
        action_safety.approved_benchmark_cost(value)


@pytest.mark.parametrize("route", ["/api/demo/load", "/api/demo/clear"])
def test_demo_actions_reject_overlapping_mutations(client, route):
    assert action_safety._DEMO_ACTION_LOCK.acquire(blocking=False)
    try:
        response = client.post(route, json={"confirm": "DELETE_ALL_DATA"})
    finally:
        action_safety._DEMO_ACTION_LOCK.release()

    assert response.status_code == 409
    assert response.get_json() == {"error": "Another demo data operation is already running."}
