"""Regression tests: one reports root, sourced from config everywhere.

Before unification (live-validation finding, 2026-06-12), config-driven
writers (CLI run, web app) saved under data/reports while ContextIndex
scanned ./reports and LocalStorage() defaulted to ./reports - so the web
could never render reports saved under reports/, and search/absorb could
never find reports saved under data/reports.

Every no-arg default must resolve through load_config()["results_dir"]
(storage.local_path, env DEEPR_REPORTS_PATH).
"""

import asyncio
import json
import logging
from pathlib import Path

import pytest
from click.testing import CliRunner

from deepr.config import load_config
from deepr.services.context_index import ContextIndex
from deepr.storage.local import LocalStorage


@pytest.fixture
def project_dir(tmp_path, monkeypatch):
    """Isolated project root: tmp cwd, no reports-path env override."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DEEPR_REPORTS_PATH", raising=False)
    return tmp_path


def _run(coro):
    return asyncio.run(coro)


def _save_report(storage: LocalStorage, job_id: str, prompt: str, body: str = "# Findings"):
    return _run(
        storage.save_report(
            job_id=job_id,
            filename="report.md",
            content=body.encode("utf-8"),
            content_type="text/markdown",
            metadata={"prompt": prompt},
        )
    )


class TestRootAgreement:
    def test_no_arg_defaults_agree_on_configured_root(self, project_dir):
        root = Path(load_config()["results_dir"])

        assert LocalStorage().base_path == (project_dir / root).resolve()
        assert ContextIndex(data_dir=project_dir / "data").reports_dir == root

    def test_env_override_flows_to_all_defaults(self, project_dir, monkeypatch):
        custom = project_dir / "custom_reports"
        monkeypatch.setenv("DEEPR_REPORTS_PATH", str(custom))

        assert load_config()["results_dir"] == str(custom)
        assert LocalStorage().base_path == custom.resolve()
        assert ContextIndex(data_dir=project_dir / "data").reports_dir == custom

    def test_saved_report_is_visible_to_context_index_scan(self, project_dir):
        """The bug: writer and scanner silently used different roots."""
        _save_report(LocalStorage(), "job-abc12345", "root unification test")

        scanned = ContextIndex(data_dir=project_dir / "data")._scan_reports()

        assert [r["metadata"]["job_id"] for r in scanned] == ["job-abc12345"]
        report_dir = scanned[0]["path"]
        assert (report_dir / "report.md").read_text(encoding="utf-8") == "# Findings"

    def test_scan_warns_about_orphans_under_legacy_root(self, project_dir, caplog):
        legacy_job = project_dir / "reports" / "2025-01-01_0900_old-topic_abc12345"
        legacy_job.mkdir(parents=True)
        (legacy_job / "metadata.json").write_text(json.dumps({"job_id": "abc12345"}), encoding="utf-8")

        with caplog.at_level(logging.WARNING, logger="deepr.services.context_index"):
            scanned = ContextIndex(data_dir=project_dir / "data")._scan_reports()

        assert scanned == []  # orphans are NOT silently absorbed
        assert any("migrate consolidate" in r.message for r in caplog.records)


class TestWebRetrieval:
    def test_completed_job_report_renders_through_web_api(self, tmp_path, monkeypatch):
        """Cross-component: a saved report must be retrievable via /api/results."""
        pytest.importorskip("flask")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-dummy-key")

        import deepr.web.app as web_app
        from deepr.queue.base import JobStatus, ResearchJob
        from deepr.queue.local_queue import SQLiteQueue

        storage = LocalStorage(str(tmp_path / "data" / "reports"))
        queue = SQLiteQueue(str(tmp_path / "queue.db"))
        job = ResearchJob(id="job-web-77777777", prompt="root unification", status=JobStatus.COMPLETED)
        _run(queue.enqueue(job))
        _save_report(storage, job.id, job.prompt, body="# Unified root report\nhttp://example.com")

        monkeypatch.setattr(web_app, "queue", queue)
        monkeypatch.setattr(web_app, "storage", storage)
        web_app.app.config.update(TESTING=True)

        resp = web_app.app.test_client().get(f"/api/results/{job.id}")

        assert resp.status_code == 200
        result = resp.get_json()["result"]
        assert "Unified root report" in result["content"]


class TestMigrateConsolidate:
    @staticmethod
    def _make_legacy_report(root: Path, name: str = "2025-01-01_0900_old-topic_abc12345"):
        job_dir = root / "reports" / name
        job_dir.mkdir(parents=True)
        (job_dir / "report.md").write_text("# Old report", encoding="utf-8")
        (job_dir / "metadata.json").write_text(json.dumps({"job_id": "abc12345"}), encoding="utf-8")
        return job_dir

    def test_moves_legacy_reports_into_configured_root(self, project_dir):
        from deepr.cli.commands.migrate import migrate

        self._make_legacy_report(project_dir)

        result = CliRunner().invoke(migrate, ["consolidate"])

        assert result.exit_code == 0
        target = project_dir / load_config()["results_dir"] / "2025-01-01_0900_old-topic_abc12345"
        assert (target / "report.md").read_text(encoding="utf-8") == "# Old report"
        assert not (project_dir / "reports").exists()

    def test_dry_run_moves_nothing(self, project_dir):
        from deepr.cli.commands.migrate import migrate

        legacy = self._make_legacy_report(project_dir)

        result = CliRunner().invoke(migrate, ["consolidate", "--dry-run"])

        assert result.exit_code == 0
        assert legacy.exists()
        assert not (project_dir / load_config()["results_dir"]).exists()

    def test_collision_is_skipped_never_overwritten(self, project_dir):
        from deepr.cli.commands.migrate import migrate

        legacy = self._make_legacy_report(project_dir)
        target = project_dir / load_config()["results_dir"] / legacy.name
        target.mkdir(parents=True)
        (target / "report.md").write_text("# Existing report", encoding="utf-8")

        result = CliRunner().invoke(migrate, ["consolidate"])

        assert result.exit_code == 0
        # Existing content untouched; colliding file stays under legacy root.
        assert (target / "report.md").read_text(encoding="utf-8") == "# Existing report"
        assert (legacy / "report.md").exists()

    def test_merges_directory_collisions_one_level(self, project_dir):
        from deepr.cli.commands.migrate import migrate

        # Both roots have a campaigns/ dir (LocalStorage creates it eagerly).
        legacy_campaign = project_dir / "reports" / "campaigns" / "campaign-001"
        legacy_campaign.mkdir(parents=True)
        (legacy_campaign / "report.md").write_text("# Campaign", encoding="utf-8")
        target_campaigns = project_dir / load_config()["results_dir"] / "campaigns"
        target_campaigns.mkdir(parents=True)

        result = CliRunner().invoke(migrate, ["consolidate"])

        assert result.exit_code == 0
        assert (target_campaigns / "campaign-001" / "report.md").exists()
        assert not (project_dir / "reports").exists()
