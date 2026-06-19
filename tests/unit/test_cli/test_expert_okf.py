"""Tests for the expert OKF export command."""

from __future__ import annotations

import json

from click.testing import CliRunner

from deepr.cli.commands.semantic.experts import expert
from deepr.cli.main import cli
from deepr.experts.profile import ExpertProfile


def test_export_okf_registered():
    assert "export-okf" in expert.commands
    opts = {param.name for param in expert.commands["export-okf"].params}
    assert {"name", "output", "force", "include_llms", "json_output"} <= opts


def test_export_okf_nonexistent_expert(monkeypatch):
    class FakeExpertStore:
        def load(self, name):
            assert name == "Ghost"
            return None

    monkeypatch.setattr("deepr.experts.profile.ExpertStore", FakeExpertStore)

    result = CliRunner().invoke(cli, ["expert", "export-okf", "Ghost", "out"])

    assert result.exit_code == 2
    assert "not found" in result.output.lower()


def test_export_okf_writes_bundle_json(monkeypatch, tmp_path):
    profile = ExpertProfile(name="OKF Expert", vector_store_id="vs-okf", domain="ai")

    class FakeExpertStore:
        def load(self, name):
            assert name == "OKF Expert"
            return profile

    monkeypatch.setattr("deepr.experts.profile.ExpertStore", FakeExpertStore)
    output = tmp_path / "bundle"

    result = CliRunner().invoke(cli, ["expert", "export-okf", "OKF Expert", str(output), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["concept_count"] == 0
    assert payload["schema_version"] == "deepr-okf-v1"
    assert (output / "index.md").exists()
    assert (output / "llms.txt").exists()
