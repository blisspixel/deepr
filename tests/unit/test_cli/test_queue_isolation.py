"""Regression coverage for CLI queue path isolation."""

from click.testing import CliRunner

from deepr.cli.main import cli
from deepr.queue import SQLiteQueue


def test_jobs_list_cannot_touch_workspace_queue(monkeypatch, tmp_path):
    workspace = tmp_path / "workspace"
    legacy_path = workspace / "queue" / "research_queue.db"
    workspace.mkdir()
    SQLiteQueue(legacy_path)
    legacy_before = legacy_path.read_bytes()

    runtime_root = tmp_path / "isolated-runtime"
    monkeypatch.chdir(workspace)
    monkeypatch.setenv("DEEPR_DATA_DIR", str(runtime_root))
    monkeypatch.delenv("DEEPR_QUEUE_DB_PATH", raising=False)

    result = CliRunner().invoke(cli, ["jobs", "list"])

    assert result.exit_code == 0, result.output
    assert (runtime_root / "queue" / "research_queue.db").exists()
    assert legacy_path.read_bytes() == legacy_before
