"""Installed configuration persists across directories without credential reloads."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from deepr import config as configuration
from deepr.cli.commands.init import _read_env_file, _resolve_data_dir_updates, _upsert_env, init
from deepr.core.settings import Settings


@pytest.fixture
def configuration_home(tmp_path, monkeypatch):
    home = tmp_path / "user"
    home.mkdir()
    working = tmp_path / "working"
    working.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(os, "environ", dict(os.environ))
    for name in tuple(os.environ):
        if name.startswith("DEEPR_") and name != "DEEPR_COST_DATA_DIR":
            os.environ.pop(name)
    monkeypatch.setattr(configuration, "_configuration_environment", None)
    monkeypatch.setattr(Settings, "_instance", None)
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "0")
    monkeypatch.chdir(working)
    monkeypatch.setattr("deepr.backends.capacity.detect_capacity", lambda **kwargs: [])
    monkeypatch.delenv("DEEPR_ENV_FILE", raising=False)
    return home


def _installed_cli(home, cwd, *arguments, overrides=None):
    """Run the registered installed CLI with isolated home and forbidden sockets."""
    source = Path(__file__).resolve().parents[3] / "src"
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("DEEPR_") and not name.endswith("_API_KEY")
    }
    env.update(
        PYTHONPATH=str(source),
        PYTHON_DOTENV_DISABLED="0",
        DEEPR_COST_DATA_DIR=str(home / "test-costs"),
        COLUMNS="400",
    )
    env.update(overrides or {})
    script = """
from pathlib import Path
from importlib.metadata import entry_points
import socket
import sys
from unittest.mock import patch

def refuse_network(*args, **kwargs):
    raise AssertionError('offline installed-entrypoint test attempted network')

socket.socket.connect = refuse_network
socket.create_connection = refuse_network
with patch.object(Path, 'home', return_value=Path(sys.argv[1])):
    import deepr
    assert Path(deepr.__file__).resolve().is_relative_to(Path(sys.argv[2]))
    import deepr.backends.capacity
    deepr.backends.capacity.detect_capacity = lambda **kwargs: []
    entrypoint = next(item for item in entry_points(group='console_scripts') if item.name == 'deepr')
    sys.argv = ['deepr', *sys.argv[3:]]
    entrypoint.load()()
"""
    return subprocess.run(
        [sys.executable, "-c", script, str(home), str(source), *arguments],
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
    )


def test_init_defaults_to_stable_user_file(configuration_home):
    Path(".env.example").write_text("UNRELATED_SETTING=must-not-copy\n", encoding="utf-8")
    result = CliRunner().invoke(init, ["--yes", "--data-dir", "chosen data"])
    assert result.exit_code == 0, result.output
    target = configuration_home / ".deepr/.env"
    assert target.is_file()
    assert not Path(".env").exists()
    values = _read_env_file(target)
    assert values["DEEPR_DATA_DIR"] == str(Path("chosen data").resolve())
    assert "UNRELATED_SETTING" not in values


def test_installed_entrypoint_reads_initialized_paths_from_unrelated_directory(configuration_home, tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "unrelated"
    first.mkdir()
    second.mkdir()
    data = first / "chosen data"
    initialized = _installed_cli(configuration_home, first, "init", "--yes", "--data-dir", str(data))
    assert initialized.returncode == 0, initialized.stdout
    inspected = _installed_cli(configuration_home, second, "config", "show")
    assert inspected.returncode == 0, inspected.stdout
    assert str(data) in inspected.stdout
    assert str(configuration_home / ".deepr/.env") in inspected.stdout
    assert "Source: defaults" not in inspected.stdout
    legacy = _installed_cli(configuration_home, second, "config", "show", "--legacy")
    assert legacy.returncode == 0, legacy.stdout
    assert str(data / "reports") in legacy.stdout
    diagnosed = _installed_cli(configuration_home, second, "doctor", "--skip-connectivity")
    assert diagnosed.returncode == 0, diagnosed.stdout
    assert str(data / "experts") in diagnosed.stdout
    assert str(data / "reports") in diagnosed.stdout
    assert str(configuration_home / ".deepr/.env") in diagnosed.stdout


def test_env_reader_understands_export_quotes_comments_and_multiline(tmp_path):
    target = tmp_path / ".env"
    target.write_text("export NAME = \"quoted value\" # keep\nMULTI='first\nsecond'\nEMPTY=\nUNSET\n", encoding="utf-8")
    assert _read_env_file(target) == {"NAME": "quoted value", "MULTI": "first\nsecond", "EMPTY": ""}


def _user_file(home, content):
    target = home / ".deepr/.env"
    target.parent.mkdir(exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def test_shared_loader_preserves_process_project_and_user_precedence(configuration_home, monkeypatch):
    user = _user_file(
        configuration_home, 'DEEPR_REPORTS_PATH="user reports"\nDEEPR_LOG_LEVEL=WARNING\nDEEPR_DEBUG=true\n'
    )
    project = Path("project config.env").resolve()
    project.write_text('DEEPR_REPORTS_PATH="project reports"\nDEEPR_LOG_LEVEL=INFO\n', encoding="utf-8")
    monkeypatch.setenv("DEEPR_ENV_FILE", str(project))
    monkeypatch.setenv("DEEPR_LOG_LEVEL", "ERROR")

    app = configuration.AppConfig.from_env()
    settings = Settings.load()
    observed = configuration.load_configuration_environment()

    assert observed.loaded_files == (str(project), str(user))
    assert settings.storage.local_path == app.storage.local_path == "project reports"
    assert settings.log_level == app.log_level == "ERROR"
    assert settings.debug is app.debug is True
    assert settings._overrides["storage.local_path"] == f"file:{project}"
    assert settings._overrides["log_level"] == "env"
    assert settings._overrides["debug"] == f"file:{user}"
    assert settings._source != "defaults"


def test_dotenv_selector_cannot_redirect_runtime_inventory_or_writes(configuration_home):
    from deepr.cli.commands import keys as keys_module
    from deepr.cli.commands.config import config

    alternate = Path("not-selected.env").resolve()
    alternate.write_text("XAI_API_KEY=unselected-key\n", encoding="utf-8")
    user = _user_file(configuration_home, f"DEEPR_ENV_FILE={alternate}\nDEEPR_REPORTS_PATH=global\n")
    observed = configuration.load_configuration_environment()

    assert observed.loaded_files == (str(user),)
    assert configuration.configuration_env_path() == user
    assert keys_module._target_env_path() == user
    assert not keys_module._key_state("xai")["present"]
    result = CliRunner().invoke(config, ["set", "DEEPR_LOG_LEVEL", "WARNING"])
    assert result.exit_code == 0, result.output
    assert _read_env_file(user)["DEEPR_LOG_LEVEL"] == "WARNING"
    assert "DEEPR_LOG_LEVEL" not in _read_env_file(alternate)


@pytest.mark.parametrize("disabled", [False, True])
def test_relative_selection_and_fallback_stay_bound_after_chdir(configuration_home, monkeypatch, tmp_path, disabled):
    from deepr.cli.commands import keys as keys_module

    user = _user_file(configuration_home, "OPENAI_API_KEY=original-user-key\n")
    selected = Path("selected.env").resolve()
    selected.write_text("XAI_API_KEY=original-selected-key\n", encoding="utf-8")
    monkeypatch.setenv("DEEPR_ENV_FILE", "selected.env")
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1" if disabled else "0")
    observed = configuration.load_configuration_environment()
    other = tmp_path / "other"
    other.mkdir()
    other.joinpath("selected.env").write_text("XAI_API_KEY=other-key\n", encoding="utf-8")
    monkeypatch.chdir(other)
    monkeypatch.setenv("DEEPR_ENV_FILE", "changed.env")
    monkeypatch.setattr(configuration, "default_data_dir", lambda: other / "different-user")

    assert observed.disabled is disabled
    assert configuration.configuration_env_path() == keys_module._target_env_path() == selected
    assert configuration.configuration_env_path(local=True) == other / ".env"
    assert keys_module._user_env_path() == user
    assert keys_module._read_env_file()["XAI_API_KEY"] == "original-selected-key"
    assert keys_module._read_env_file()["OPENAI_API_KEY"] == "original-user-key"
    keys_module._write_env_key("ANTHROPIC_API_KEY", "stored-without-reinjection")
    assert _read_env_file(selected)["ANTHROPIC_API_KEY"] == "stored-without-reinjection"
    assert "ANTHROPIC_API_KEY" not in os.environ
    assert not other.joinpath("changed.env").exists()
    if disabled:
        assert observed.loaded_files == ()
        assert "XAI_API_KEY" not in os.environ


@pytest.mark.parametrize("disabled", ["1", "true", "t", "yes", "y"])
def test_disabled_loading_reads_no_files(configuration_home, monkeypatch, disabled):
    _user_file(configuration_home, "DEEPR_REPORTS_PATH=must-not-load\nOPENAI_API_KEY=must-not-load\n")
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", disabled)
    monkeypatch.setenv("DEEPR_REPORTS_PATH", "process reports")
    monkeypatch.setattr(configuration, "dotenv_values", lambda *args, **kwargs: pytest.fail("dotenv file read"))
    settings = Settings.load()
    assert settings.storage.local_path == "process reports"
    assert configuration.load_configuration_environment().disabled
    assert configuration.load_configuration_environment().loaded_files == ()
    assert "disabled" in settings.show()


def test_missing_selected_file_reports_fallback_and_provenance(configuration_home, monkeypatch):
    user = _user_file(configuration_home, "DEEPR_REPORTS_PATH=fallback\n")
    missing = Path("not-created.env").resolve()
    monkeypatch.setenv("DEEPR_ENV_FILE", str(missing))
    settings = Settings.load()
    observed = settings.to_dict()["_environment"]
    assert settings.storage.local_path == "fallback"
    assert observed["loaded_files"] == (str(user),)
    assert observed["missing_files"] == (str(missing),)
    from deepr.cli.commands.doctor import check_configuration_sources

    diagnostic = check_configuration_sources()[0]
    assert str(user) in diagnostic.message
    assert f"Not found: {missing}" in diagnostic.details
    from deepr.cli.commands import keys as keys_module

    monkeypatch.setenv("DEEPR_ENV_FILE", "not-the-startup-selection.env")
    keys_module._write_env_key("OPENAI_API_KEY", "new-key-not-in-runtime")
    assert _read_env_file(missing)["OPENAI_API_KEY"] == "new-key-not-in-runtime"
    assert "OPENAI_API_KEY" not in _read_env_file(user)
    assert "OPENAI_API_KEY" not in os.environ
    assert configuration.load_configuration_environment().missing_files == (str(missing),)


def test_later_settings_and_app_access_cannot_restore_quarantined_keys(configuration_home, monkeypatch):
    secret = "test-synthetic-credential-do-not-print"
    user = _user_file(configuration_home, f"OPENAI_API_KEY={secret}\nDEEPR_REPORTS_PATH=chosen\n")
    configuration.load_configuration_environment()
    from deepr.security.key_quarantine import QUARANTINE_PREFIX, quarantine_metered_keys

    assert os.environ["OPENAI_API_KEY"] == secret
    quarantine_metered_keys()
    user.write_text(f"OPENAI_API_KEY={secret}-changed\nDEEPR_REPORTS_PATH=changed\n", encoding="utf-8")
    monkeypatch.setenv("DEEPR_ENV_FILE", "unselected-after-quarantine.env")
    app = configuration.AppConfig.from_env()
    settings = Settings.load(reset_singleton=True)
    assert "OPENAI_API_KEY" not in os.environ
    assert os.environ[QUARANTINE_PREFIX + "OPENAI_API_KEY"] == secret
    assert app.provider.openai_api_key is None
    assert settings.get_api_key("openai") == ""
    assert settings.storage.local_path == "chosen"
    from deepr.cli.commands import keys as keys_module

    assert configuration.configuration_env_path() == keys_module._target_env_path() == user
    assert keys_module._key_state("openai")["effective_value"] == secret
    assert secret not in json.dumps(settings.to_dict())
    from deepr.cli.commands.doctor import check_configuration_sources

    diagnostic = check_configuration_sources()[0]
    assert secret not in diagnostic.message + repr(diagnostic.details)
    assert f"OPENAI_API_KEY: file:{user}" in diagnostic.details


@pytest.mark.parametrize("value", ["folder with spaces", 'folder with "quotes"', "folder's path", "C:\\some\\\\folder"])
def test_writer_round_trips_paths_and_preserves_unrelated_entries(configuration_home, value):
    target = Path("project.env")
    preserved = "# header\nexport KEEP = \"kept value\" # comment\nMULTI='first\nsecond'\n"
    target.write_text(preserved + "DEEPR_DATA_DIR=old\n", encoding="utf-8")
    _upsert_env(target, {"DEEPR_DATA_DIR": value})
    assert target.read_text(encoding="utf-8").startswith(preserved)
    assert _read_env_file(target)["DEEPR_DATA_DIR"] == value
    assert _read_env_file(target)["KEEP"] == "kept value"
    assert target.read_text(encoding="utf-8").count("DEEPR_DATA_DIR=") == 1


def test_explicit_data_directory_normalizes_root_and_relative_paths(configuration_home):
    root = Path.cwd().anchor
    updates = _resolve_data_dir_updates({}, yes=True, data_dir=root)
    assert updates["DEEPR_DATA_DIR"] == root
    assert updates["DEEPR_REPORTS_PATH"] == str(Path(root) / "reports")
    updates = _resolve_data_dir_updates({}, yes=True, data_dir="relative folder")
    assert updates["DEEPR_DATA_DIR"] == str(Path("relative folder").resolve())


def test_init_local_env_requires_explicit_selection_for_later_invocations(configuration_home):
    result = CliRunner().invoke(init, ["--yes", "--local-env", "--data-dir", "local data"])
    assert result.exit_code == 0, result.output
    assert Path(".env").is_file()
    assert not (configuration_home / ".deepr/.env").exists()
    assert "DEEPR_ENV_FILE" in result.output
    inspected = _installed_cli(configuration_home, Path.cwd(), "config", "show")
    assert "local data" not in inspected.stdout
    selected = _installed_cli(
        configuration_home, Path.cwd(), "config", "show", overrides={"DEEPR_ENV_FILE": str(Path(".env").resolve())}
    )
    assert selected.returncode == 0, selected.stdout
    assert "local data" in selected.stdout


def test_installed_entrypoint_ignores_ambient_current_and_parent_files(configuration_home):
    Path(".env").write_text("DEEPR_REPORTS_PATH=ambient-injection\nOPENAI_API_KEY=ambient-secret\n", encoding="utf-8")
    Path.cwd().parent.joinpath(".env").write_text("DEEPR_DATA_DIR=parent-injection\n", encoding="utf-8")
    result = _installed_cli(configuration_home, Path.cwd(), "config", "show")
    assert result.returncode == 0, result.stdout
    assert "ambient-injection" not in result.stdout
    assert "parent-injection" not in result.stdout
    assert "ambient-secret" not in result.stdout
    assert "none loaded" in result.stdout


def test_config_set_creates_private_global_file_and_never_echoes_secrets(configuration_home):
    from deepr.cli.commands.config import config

    secret = "synthetic secret with spaces"
    result = CliRunner().invoke(config, ["set", "OPENAI_API_KEY", secret])
    assert result.exit_code == 0, result.output
    assert secret not in result.output
    target = configuration_home / ".deepr/.env"
    assert _read_env_file(target)["OPENAI_API_KEY"] == secret
    assert not Path(".env").exists()
    if os.name == "posix":
        assert target.stat().st_mode & 0o077 == 0
        assert target.parent.stat().st_mode & 0o077 == 0


def test_init_selected_project_file_and_existing_values_are_preserved(configuration_home, monkeypatch):
    selected = Path("settings/selected.env").resolve()
    selected.parent.mkdir()
    selected.write_text('# retained comment\nDEEPR_MAX_COST_PER_JOB="0.25"\n', encoding="utf-8")
    monkeypatch.setenv("DEEPR_ENV_FILE", str(selected))
    result = CliRunner().invoke(init, ["--yes"])
    assert result.exit_code == 0, result.output
    assert _read_env_file(selected)["DEEPR_MAX_COST_PER_JOB"] == "0.25"
    assert "# retained comment" in selected.read_text(encoding="utf-8")
    assert not (configuration_home / ".deepr/.env").exists()


def test_init_without_data_relocation_preserves_existing_split_defaults(configuration_home):
    result = CliRunner().invoke(init, ["--yes"])
    assert result.exit_code == 0, result.output
    settings = Settings.load()
    assert settings.data_dir == "data"
    assert settings.storage.local_path == "data/reports"
    assert configuration.experts_root() == configuration_home / ".deepr/experts"
    assert configuration.queue_db_path() == "queue/research_queue.db"


def test_keys_inventory_ignores_ambient_files_and_parses_selected_quotes(configuration_home, monkeypatch):
    from deepr.cli.commands import keys as keys_module

    Path(".env").write_text("XAI_API_KEY=ambient-credential\n", encoding="utf-8")
    _user_file(configuration_home, "OPENAI_API_KEY='user quoted key'\n")
    assert not keys_module._key_state("xai")["present"]
    selected = Path("selected.env").resolve()
    selected.write_text('export XAI_API_KEY = "selected quoted key" # comment\n', encoding="utf-8")
    monkeypatch.setenv("DEEPR_ENV_FILE", str(selected))
    # A fresh invocation selects this file; inventory itself does not inject keys.
    monkeypatch.setattr(configuration, "_configuration_environment", None)
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    assert keys_module._key_state("xai")["effective_value"] == "selected quoted key"
    assert keys_module._key_state("openai")["effective_value"] == "user quoted key"
    assert "XAI_API_KEY" not in os.environ
    result = CliRunner().invoke(keys_module.keys, ["list", "--json"])
    assert "selected quoted key" not in result.output
    assert "user quoted key" not in result.output


def test_keys_write_defaults_to_user_even_with_ambient_file(configuration_home):
    from deepr.cli.commands import keys as keys_module

    ambient = Path(".env")
    ambient.write_text("KEEP=untouched\n", encoding="utf-8")
    target = keys_module._write_env_key("OPENAI_API_KEY", "quoted 'key' with \\slashes")
    assert target == configuration_home / ".deepr/.env"
    assert _read_env_file(target)["OPENAI_API_KEY"] == "quoted 'key' with \\slashes"
    assert ambient.read_text(encoding="utf-8") == "KEEP=untouched\n"


@pytest.mark.parametrize("module", ["deepr.web.app", "deepr.api.app"])
def test_http_app_imports_do_not_load_ambient_files_or_restore_keys(configuration_home, module):
    _user_file(configuration_home, "DEEPR_REPORTS_PATH=chosen-reports\nOPENAI_API_KEY=chosen-synthetic-key\n")
    Path(".env").write_text("DEEPR_LOG_LEVEL=ambient-level\nXAI_API_KEY=ambient-synthetic-key\n", encoding="utf-8")
    source = Path(__file__).resolve().parents[3] / "src"
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("DEEPR_") and not name.endswith("_API_KEY")
    }
    env.update(
        PYTHONPATH=str(source), PYTHON_DOTENV_DISABLED="0", DEEPR_COST_DATA_DIR=str(configuration_home / "test-costs")
    )
    script = """
import importlib
import os
from pathlib import Path
import socket
import sys
from unittest.mock import patch

def refuse_network(*args, **kwargs):
    raise AssertionError('HTTP app import attempted network')

socket.socket.connect = refuse_network
socket.create_connection = refuse_network
with patch.object(Path, 'home', return_value=Path(sys.argv[1])):
    from deepr.config import load_configuration_environment
    from deepr.security.key_quarantine import quarantine_metered_keys
    load_configuration_environment()
    quarantine_metered_keys()
    importlib.import_module(sys.argv[2])
    assert os.environ.get('OPENAI_API_KEY') is None
    assert os.environ.get('XAI_API_KEY') is None
    assert os.environ.get('DEEPR_LOG_LEVEL') is None
    assert os.environ['DEEPR_REPORTS_PATH'] == 'chosen-reports'
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(configuration_home), module],
        cwd=Path.cwd(),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout


@pytest.mark.parametrize("operation", ["read", "write"])
def test_keys_file_size_bounds_remain(configuration_home, operation):
    import click

    from deepr.cli.commands import keys as keys_module

    target = Path("oversized.env")
    target.write_text("#" * (keys_module._MAX_ENV_BYTES + 1), encoding="utf-8")
    with pytest.raises(click.ClickException, match="too large"):
        if operation == "read":
            keys_module._parse_env_file(target)
        else:
            keys_module._write_env_key("OPENAI_API_KEY", "synthetic", path=target)


def test_explicit_empty_process_value_still_wins(configuration_home, monkeypatch):
    _user_file(configuration_home, "DEEPR_LOG_LEVEL=DEBUG\nDEEPR_DEBUG=true\n")
    monkeypatch.setenv("DEEPR_LOG_LEVEL", "")
    monkeypatch.setenv("DEEPR_DEBUG", "")
    settings = Settings.load()
    app = configuration.AppConfig.from_env()
    assert settings.log_level == app.log_level == ""
    assert settings.debug is app.debug is False
    assert settings._overrides["log_level"] == "env"


def test_dotenv_expansion_keeps_process_value_precedence(configuration_home, monkeypatch):
    _user_file(configuration_home, "BASE=file-root\nDEEPR_REPORTS_PATH=${BASE}/reports\n")
    monkeypatch.setenv("BASE", "process-root")
    assert Settings.load().storage.local_path == "process-root/reports"
