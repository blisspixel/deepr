"""Storage inspection resolves configured paths without changing or creating them."""

from pathlib import Path

from click.testing import CliRunner


def test_doctor_uses_resolved_canonical_roots(monkeypatch, tmp_path):
    from deepr.cli.commands.doctor import check_storage_locations

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("deepr.config.experts_root", lambda: Path("experts-here"))
    monkeypatch.setattr("deepr.config.load_config", lambda: {"results_dir": "reports-here"})
    checks = {item.name: item for item in check_storage_locations()}
    assert checks["Experts"].message == str(tmp_path / "experts-here")
    assert checks["Research reports"].message == str(tmp_path / "reports-here")
    assert not (tmp_path / "experts-here").exists()
    assert not (tmp_path / "reports-here").exists()


def test_settings_display_resolves_without_mutating_config(monkeypatch, tmp_path):
    from deepr.core.settings import Settings

    monkeypatch.chdir(tmp_path)
    settings = Settings(data_dir="relative-data")
    settings.storage.local_path = "relative-reports"
    output = settings.show()
    assert f"Data Dir: {tmp_path / 'relative-data'}" in output
    assert f"Path: {tmp_path / 'relative-reports'}" in output
    assert settings.data_dir == "relative-data"
    assert settings.storage.local_path == "relative-reports"
    assert not (tmp_path / "relative-data").exists()
    assert not (tmp_path / "relative-reports").exists()


def test_legacy_config_display_resolves_canonical_paths(monkeypatch, tmp_path):
    from deepr.cli.commands.config import config

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "deepr.config.load_config", lambda: {"queue_db_path": "queue/jobs.db", "results_dir": "reports"}
    )
    result = CliRunner().invoke(config, ["show", "--legacy"])
    assert result.exit_code == 0, result.output
    assert str(tmp_path / "queue/jobs.db") in result.output
    assert str(tmp_path / "reports") in result.output
    assert not (tmp_path / "queue").exists()
