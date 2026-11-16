"""Tests for benchmark preference loading in ProviderConfig."""

import json

from deepr.config import ProviderConfig

_SHIPPED_TASK_MODELS = dict(ProviderConfig.model_fields["TASK_MODEL_MAP"].default)
_PROVIDER_KEYS = (
    "OPENAI_API_KEY",
    "XAI_API_KEY",
    "GEMINI_API_KEY",
    "ANTHROPIC_API_KEY",
    "AZURE_PROJECT_ENDPOINT",
)


def _isolate_routing(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DEEPR_DATA_DIR", raising=False)
    monkeypatch.delenv("DEEPR_DEEP_RESEARCH_MODEL", raising=False)
    monkeypatch.setenv("DEEPR_USE_BENCHMARK_ROUTING", "true")
    for name in _PROVIDER_KEYS:
        monkeypatch.delenv(name, raising=False)


def _write_preferences(tmp_path, task_preferences: dict[str, str]) -> None:
    bench_dir = tmp_path / "data" / "benchmarks"
    bench_dir.mkdir(parents=True, exist_ok=True)
    payload = {"task_preferences": {task: {"best_value": model} for task, model in task_preferences.items()}}
    (bench_dir / "routing_preferences.json").write_text(json.dumps(payload), encoding="utf-8")


def _shipped_default_unchanged() -> None:
    assert dict(ProviderConfig.model_fields["TASK_MODEL_MAP"].default) == _SHIPPED_TASK_MODELS


def test_provider_config_logs_warning_on_invalid_routing_preferences(tmp_path, monkeypatch, caplog):
    bench_dir = tmp_path / "data" / "benchmarks"
    bench_dir.mkdir(parents=True)
    (bench_dir / "routing_preferences.json").write_text("{invalid json", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPR_USE_BENCHMARK_ROUTING", "true")

    with caplog.at_level("WARNING"):
        _ = ProviderConfig()

    assert "Could not load benchmark preferences for config" in caplog.text


def test_benchmark_preferences_skip_models_automatic_routing_refuses(tmp_path, monkeypatch):
    """A saved winner cannot put a shut-down or unregistered id on the task map."""
    _isolate_routing(monkeypatch, tmp_path)
    for name in _PROVIDER_KEYS:
        monkeypatch.setenv(name, "present")
    _write_preferences(
        tmp_path,
        {
            "comprehensive_research": "openai/o3-deep-research",
            "synthesis": "openai/gpt-6-sol",
            "reasoning": "openai/gpt-5",
            "quick_lookup": "openai/o4-mini",
            "technical_docs": "anthropic/claude-sonnet-4-5",
            "multi_source_synthesis": "xai/grok-4",
        },
    )

    config = ProviderConfig()

    assert config.TASK_MODEL_MAP == _SHIPPED_TASK_MODELS
    _shipped_default_unchanged()


def test_benchmark_preferences_keep_gpt6_research_name_guard(tmp_path, monkeypatch):
    """GPT-6 research ids stay off the deep-research name gate."""
    _isolate_routing(monkeypatch, tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "present")
    _write_preferences(tmp_path, {"comprehensive_research": "openai/gpt-6.1-terra"})

    config = ProviderConfig()

    assert config.TASK_MODEL_MAP["deep_research"] == ("openai", "gpt-6.1-sol")
    _shipped_default_unchanged()


def test_benchmark_preferences_apply_selectable_registered_models(tmp_path, monkeypatch):
    """A current registered id can still override the task it won."""
    _isolate_routing(monkeypatch, tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "present")
    monkeypatch.setenv("GEMINI_API_KEY", "present")
    _write_preferences(
        tmp_path,
        {
            "synthesis": "openai/gpt-6.1-terra",
            "comprehensive_research": "gemini/deep-research",
            "multi_source_synthesis": "openai/gpt-5.6-sol",
        },
    )

    config = ProviderConfig()

    assert config.TASK_MODEL_MAP["synthesis"] == ("openai", "gpt-6.1-terra")
    assert config.TASK_MODEL_MAP["deep_research"] == ("gemini", "deep-research")
    assert config.TASK_MODEL_MAP["strategy"] == ("openai", "gpt-5.6-sol")
    assert config.TASK_MODEL_MAP["chat"] == _SHIPPED_TASK_MODELS["chat"]
    assert config.TASK_MODEL_MAP["quick_lookup"] == _SHIPPED_TASK_MODELS["quick_lookup"]
    _shipped_default_unchanged()


def test_benchmark_preferences_ignore_a_non_string_best_value(tmp_path, monkeypatch):
    _isolate_routing(monkeypatch, tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "present")
    bench_dir = tmp_path / "data" / "benchmarks"
    bench_dir.mkdir(parents=True)
    payload = {
        "task_preferences": {
            "synthesis": {"best_value": None},
            "comprehensive_research": {"best_value": 6},
            "reasoning": "openai/gpt-6.1-terra",
        }
    }
    (bench_dir / "routing_preferences.json").write_text(json.dumps(payload), encoding="utf-8")

    config = ProviderConfig()

    assert config.TASK_MODEL_MAP == _SHIPPED_TASK_MODELS


def test_benchmark_preferences_need_the_provider_key(tmp_path, monkeypatch):
    _isolate_routing(monkeypatch, tmp_path)
    _write_preferences(tmp_path, {"synthesis": "openai/gpt-6.1-terra"})

    config = ProviderConfig()

    assert config.TASK_MODEL_MAP == _SHIPPED_TASK_MODELS


def test_deep_research_model_env_beats_a_selectable_preference(tmp_path, monkeypatch):
    _isolate_routing(monkeypatch, tmp_path)
    monkeypatch.setenv("DEEPR_DEEP_RESEARCH_MODEL", "gpt-6.1-sol")
    monkeypatch.setenv("GEMINI_API_KEY", "present")
    _write_preferences(tmp_path, {"comprehensive_research": "gemini/deep-research"})

    config = ProviderConfig()

    assert config.TASK_MODEL_MAP["deep_research"] == ("openai", "gpt-6.1-sol")
    assert config.deep_research_model == "gpt-6.1-sol"
