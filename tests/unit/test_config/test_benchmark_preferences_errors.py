"""Tests for benchmark preference parse error visibility in ProviderConfig."""

from deepr.config import ProviderConfig


def test_provider_config_logs_warning_on_invalid_routing_preferences(tmp_path, monkeypatch, caplog):
    bench_dir = tmp_path / "data" / "benchmarks"
    bench_dir.mkdir(parents=True)
    (bench_dir / "routing_preferences.json").write_text("{invalid json", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPR_USE_BENCHMARK_ROUTING", "true")

    with caplog.at_level("WARNING"):
        _ = ProviderConfig()

    assert "Could not load benchmark preferences for config" in caplog.text
