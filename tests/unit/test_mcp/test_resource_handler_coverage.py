"""Coverage tests for ``MCPResourceHandler`` read paths.

Targets the report/log file readers and the campaign/expert routing branches
that were previously not exercised by ``test_resource_handler.py``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.mcp.state.resource_handler import MCPResourceHandler


@pytest.fixture
def handler(tmp_path):
    return MCPResourceHandler(reports_base=tmp_path / "reports", db_path=False)


@pytest.fixture
def job_dir(tmp_path):
    d = tmp_path / "reports" / "job_xyz"
    d.mkdir(parents=True)
    return d


class TestReadResource:
    def test_invalid_uri(self, handler):
        r = handler.read_resource("not-a-valid-uri")
        assert r.success is False
        assert "Invalid" in r.error

    def test_unknown_resource_type(self, handler):
        r = handler.read_resource("deepr://unknown/abc/sub")
        # Either the parser rejects it or the handler reports unknown.
        assert r.success is False


class TestCampaignResources:
    def test_status_missing_job(self, handler):
        r = handler.read_resource("deepr://campaigns/ghost/status")
        assert r.success is False
        assert "Job not found" in r.error

    def test_plan_missing(self, handler):
        r = handler.read_resource("deepr://campaigns/ghost/plan")
        assert r.success is False

    def test_beliefs_missing(self, handler):
        r = handler.read_resource("deepr://campaigns/ghost/beliefs")
        assert r.success is False

    def test_unknown_subresource(self, handler):
        r = handler.read_resource("deepr://campaigns/ghost/weird")
        assert r.success is False


class TestReportResources:
    def test_final_md_returns_content(self, handler, job_dir):
        (job_dir / "report.md").write_text("# Report\n\nbody")
        r = handler.read_resource(f"deepr://reports/{job_dir.name}/final.md")
        assert r.success is True
        assert r.data["format"] == "markdown"
        assert "Report" in r.data["content"]

    def test_final_md_missing(self, handler, job_dir):
        r = handler.read_resource(f"deepr://reports/{job_dir.name}/final.md")
        assert r.success is False
        assert "not found" in r.error

    def test_summary_json_from_metadata(self, handler, job_dir):
        (job_dir / "metadata.json").write_text(json.dumps({"cost": 1.5}))
        r = handler.read_resource(f"deepr://reports/{job_dir.name}/summary.json")
        assert r.success is True
        assert r.data["cost"] == 1.5

    def test_summary_json_falls_back_to_job_state(self, handler, job_dir):
        # No file present - should fall through to JobManager state, which is None.
        r = handler.read_resource(f"deepr://reports/{job_dir.name}/summary.json")
        assert r.success is False

    def test_unknown_report_subresource(self, handler, job_dir):
        r = handler.read_resource(f"deepr://reports/{job_dir.name}/unknown")
        assert r.success is False

    def test_path_traversal_blocked(self, handler):
        # ".." in job_id makes resolved path escape reports_base - the
        # resolve().is_relative_to check should reject it.
        r = handler.read_resource("deepr://reports/..%2F..%2Fetc%2Fpasswd/final.md")
        # Either invalid URI or invalid job_id; both are failure states.
        assert r.success is False


class TestLogResources:
    def test_search_trace_json(self, handler, job_dir):
        trace = [{"query": "q1"}, {"query": "q2"}]
        (job_dir / "search_trace.json").write_text(json.dumps(trace))
        r = handler.read_resource(f"deepr://logs/{job_dir.name}/search_trace.json")
        assert r.success is True
        assert r.data == trace

    def test_search_trace_fallback_name(self, handler, job_dir):
        trace = {"steps": []}
        (job_dir / "trace.json").write_text(json.dumps(trace))
        r = handler.read_resource(f"deepr://logs/{job_dir.name}/search_trace.json")
        assert r.success is True

    def test_decisions_md(self, handler, job_dir):
        (job_dir / "decisions.md").write_text("- decided to do X")
        r = handler.read_resource(f"deepr://logs/{job_dir.name}/decisions.md")
        assert r.success is True
        assert r.data["format"] == "markdown"

    def test_unknown_log_subresource(self, handler, job_dir):
        r = handler.read_resource(f"deepr://logs/{job_dir.name}/unknown.txt")
        assert r.success is False

    def test_missing_log_files(self, handler, job_dir):
        r = handler.read_resource(f"deepr://logs/{job_dir.name}/decisions.md")
        assert r.success is False
        assert "not found" in r.error

    def test_invalid_json_log(self, handler, job_dir):
        (job_dir / "search_trace.json").write_text("definitely not json")
        r = handler.read_resource(f"deepr://logs/{job_dir.name}/search_trace.json")
        assert r.success is False


class TestExpertResource:
    def test_unknown_expert_returns_error(self, handler):
        # ExpertResourceManager.resolve_uri returns None for unknown expert.
        r = handler.read_resource("deepr://experts/ghost/profile")
        assert r.success is False

    def test_known_expert_via_resolve_uri(self, handler):
        # Patch resolve_uri on the real ExpertResourceManager.
        handler._experts.resolve_uri = MagicMock(return_value={"name": "alice"})
        r = handler.read_resource("deepr://experts/alice/profile")
        assert r.success is True
        assert r.data == {"name": "alice"}


class TestListResources:
    def test_unknown_filter_returns_empty(self, handler):
        urls = handler.list_resources(resource_type="other")
        # Implementation only iterates the four known types; an unknown
        # filter should produce an empty list.
        assert urls == []

    def test_filter_to_campaigns(self, handler):
        urls = handler.list_resources(resource_type="campaigns")
        # No jobs registered - campaigns list comes back empty.
        assert isinstance(urls, list)
