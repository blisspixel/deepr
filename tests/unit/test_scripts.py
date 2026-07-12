from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load_script_module(monkeypatch: pytest.MonkeyPatch, filename: str) -> types.ModuleType:
    script_path = ROOT / "scripts" / filename
    module_name = f"script_test_{script_path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    return module


def _script_env(tmp_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["DEEPR_DATA_DIR"] = str(tmp_path / "data")
    env["DEEPR_COST_DATA_DIR"] = str(tmp_path / "costs")
    env["DEEPR_REPORTS_PATH"] = str(tmp_path / "reports")
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    return env


def test_discover_models_show_registry_uses_src_layout(tmp_path: Path):
    result = subprocess.run(
        [sys.executable, "scripts/discover_models.py", "--show-registry"],
        cwd=ROOT,
        env=_script_env(tmp_path),
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "openai/gpt-5.4" in result.stdout
    assert "src/deepr/providers/registry.py" not in result.stderr


def test_analyze_doc_gaps_blocks_before_env_or_client_construction(monkeypatch, capsys):
    calls: list[str] = []

    fake_dotenv = types.ModuleType("dotenv")

    def forbidden_env_load(*_args, **_kwargs):
        calls.append("dotenv")
        raise AssertionError("documentation analysis loaded .env before the metered gate")

    fake_dotenv.load_dotenv = forbidden_env_load  # type: ignore[attr-defined]
    fake_openai = types.ModuleType("openai")

    class ForbiddenOpenAI:
        def __init__(self, *_args, **_kwargs):
            calls.append("openai")
            raise AssertionError("documentation analysis constructed a client before the metered gate")

    fake_openai.OpenAI = ForbiddenOpenAI  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "dotenv", fake_dotenv)
    monkeypatch.setitem(sys.modules, "openai", fake_openai)
    module = _load_script_module(monkeypatch, "analyze_doc_gaps.py")

    assert module.main() == 2
    assert calls == []
    assert "metered_expert_mutation_accounting_unavailable" in capsys.readouterr().out


def test_discover_models_llm_blocks_before_registry_or_model_work(monkeypatch, capsys):
    module = _load_script_module(monkeypatch, "discover_models.py")

    with pytest.raises(module.MeteredExpertMutationDisabledError):
        module.discover_via_llm()

    def unexpected_work(*_args, **_kwargs):
        raise AssertionError("LLM discovery reached work before the metered gate")

    monkeypatch.setattr(module, "load_registry", unexpected_work)
    monkeypatch.setattr(module, "preflight_check", unexpected_work)
    monkeypatch.setattr(module, "discover_via_llm", unexpected_work)
    monkeypatch.setattr(sys, "argv", ["discover_models.py", "--llm"])

    with pytest.raises(SystemExit) as exc_info:
        module.main()

    assert exc_info.value.code == 2
    assert "metered_expert_mutation_accounting_unavailable" in capsys.readouterr().out


def test_discover_models_read_only_api_listing_remains_available(monkeypatch, capsys):
    module = _load_script_module(monkeypatch, "discover_models.py")
    discovered = module.DiscoveredModel(provider="openai", model_id="gpt-test", source="api")

    monkeypatch.setattr(
        module,
        "require_metered_expert_mutation",
        lambda *_args, **_kwargs: pytest.fail("read-only API listing used the metered model-call gate"),
    )
    monkeypatch.setattr(module, "load_registry", lambda: {})
    monkeypatch.setattr(module, "preflight_check", lambda _providers: {"openai": True})
    monkeypatch.setattr(module, "discover_via_api", lambda providers: [discovered])
    monkeypatch.setattr(sys, "argv", ["discover_models.py", "--format", "json"])

    module.main()

    assert '"model_id": "gpt-test"' in capsys.readouterr().out


def test_create_demo_experts_uses_configured_experts_root(tmp_path: Path):
    result = subprocess.run(
        [sys.executable, "scripts/create_demo_experts.py"],
        cwd=ROOT,
        env=_script_env(tmp_path),
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    profile_paths = sorted((tmp_path / "data" / "experts").rglob("profile.json"))
    assert len(profile_paths) == 3
    worldview_paths = sorted((tmp_path / "data" / "experts").rglob("worldview.json"))
    assert len(worldview_paths) == 3
    for worldview_path in worldview_paths:
        worldview = json.loads(worldview_path.read_text(encoding="utf-8"))
        assert len(worldview["beliefs"]) > 0
        assert len(worldview["knowledge_gaps"]) > 0
        for belief in worldview["beliefs"]:
            assert belief["statement"]
            assert belief["confidence"] > 0
            assert len(belief["evidence"]) > 0
    assert "Created 'Climate Science'" in result.stdout


def test_create_demo_experts_refreshes_stale_demo_profiles(tmp_path: Path):
    env = _script_env(tmp_path)
    first = subprocess.run(
        [sys.executable, "scripts/create_demo_experts.py"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert first.returncode == 0, first.stderr

    profile_path = next(
        path
        for path in (tmp_path / "data" / "experts").rglob("profile.json")
        if json.loads(path.read_text(encoding="utf-8"))["name"] == "Climate Science"
    )
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile["source_files"] = []
    profile["total_documents"] = 0
    profile["description"] = "IPCC reports, carbon budgets, climate modeling, and emissions pathways"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")

    second = subprocess.run(
        [sys.executable, "scripts/create_demo_experts.py"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert second.returncode == 0, second.stderr
    refreshed = json.loads(profile_path.read_text(encoding="utf-8"))
    assert refreshed["total_documents"] == 12
    assert len(refreshed["source_files"]) == 12
    assert refreshed["knowledge_cutoff_date"]
    assert "Refreshed 'Climate Science'" in second.stdout


def test_check_costs_reads_canonical_ledger(tmp_path: Path):
    cost_dir = tmp_path / "costs"
    cost_dir.mkdir(parents=True)
    (cost_dir / "cost_ledger.jsonl").write_text(
        json.dumps(
            {
                "timestamp": "2026-07-12T10:00:00+00:00",
                "operation": "expert_consult",
                "provider": "local",
                "model": "qwen",
                "cost_usd": 0.0,
                "source": "test",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "scripts/check_costs.py"],
        cwd=ROOT,
        env=_script_env(tmp_path),
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert f"Canonical ledger: {cost_dir / 'cost_ledger.jsonl'}" in result.stdout
    assert "expert_consult [local]" in result.stdout
    assert "All-time canonical total: $0.000000" in result.stdout


def test_documentation_batch_script_fails_before_provider_work(tmp_path: Path):
    env = _script_env(tmp_path)
    env["OPENAI_API_KEY"] = "must-not-be-used"

    result = subprocess.run(
        [sys.executable, "scripts/submit_doc_research_jobs.py"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 2
    assert "research_parent_budget_unavailable" in result.stdout
    assert not (tmp_path / "data").exists()
