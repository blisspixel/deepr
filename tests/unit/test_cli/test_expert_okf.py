"""Tests for the expert OKF export command."""

from __future__ import annotations

import json
from types import SimpleNamespace

from click.testing import CliRunner

from deepr.cli.commands.semantic.experts import expert
from deepr.cli.main import cli
from deepr.experts.beliefs import Belief, BeliefStore
from deepr.experts.okf import build_okf_bundle, write_okf_bundle
from deepr.experts.profile import ExpertProfile


def test_export_okf_registered():
    assert "export-okf" in expert.commands
    opts = {param.name for param in expert.commands["export-okf"].params}
    assert {"name", "output", "force", "include_llms", "json_output"} <= opts
    assert "absorb-okf" in expert.commands
    absorb_opts = {param.name for param in expert.commands["absorb-okf"].params}
    assert {"name", "path", "dry_run", "local", "api", "json_output"} <= absorb_opts


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


def test_absorb_okf_rejects_local_and_api_together():
    result = CliRunner().invoke(cli, ["expert", "absorb-okf", "OKF Expert", ".", "--local", "--api"])

    assert result.exit_code == 2
    assert "not both" in result.output


def test_absorb_okf_local_dry_run_routes_parsed_text_to_absorber(monkeypatch, tmp_path):
    captured = {}
    profile = ExpertProfile(name="OKF Expert", vector_store_id="vs-okf", domain="ai")
    store = BeliefStore("OKF Expert", storage_dir=tmp_path / "beliefs")
    store.add_belief(Belief("OKF claims need verification", 0.9, domain="ai"), check_conflicts=False)
    bundle = build_okf_bundle(profile, store, manifest=profile.get_manifest())
    okf_dir = tmp_path / "okf"
    write_okf_bundle(bundle, okf_dir)

    class FakeExpertStore:
        def load(self, name):
            assert name == "OKF Expert"
            return profile

        def save(self, saved_profile):
            captured["saved_profile"] = saved_profile

    class FakeReportAbsorber:
        def __init__(self, loaded_profile, *, model, client, estimated_cost=0.0):
            captured["profile"] = loaded_profile
            captured["model"] = model
            captured["client"] = client
            captured["estimated_cost"] = estimated_cost

        async def absorb(self, report_id, report_text, *, min_confidence, dry_run):
            captured["report_id"] = report_id
            captured["report_text"] = report_text
            captured["min_confidence"] = min_confidence
            captured["dry_run"] = dry_run
            return SimpleNamespace(
                dry_run=True,
                estimated_cost=0.0,
                total_candidates=1,
                absorbed=[],
                flagged=[],
                to_dict=lambda: {"dry_run": True, "absorbed_count": 0},
            )

    monkeypatch.setattr("deepr.experts.profile.ExpertStore", FakeExpertStore)
    monkeypatch.setattr("deepr.experts.report_absorber.ReportAbsorber", FakeReportAbsorber)
    monkeypatch.setattr("deepr.backends.local.default_local_model", lambda: "qwen-local")
    monkeypatch.setattr("deepr.backends.local.ollama_chat_client", lambda: "client")

    result = CliRunner().invoke(
        cli,
        ["expert", "absorb-okf", "OKF Expert", str(okf_dir), "--local", "--dry-run", "--yes", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["okf"]["concept_count"] == 1
    assert payload["absorption"]["dry_run"] is True
    assert captured["model"] == "qwen-local"
    assert captured["estimated_cost"] == 0.0
    assert captured["dry_run"] is True
    assert captured["report_id"].startswith("okf:okf:")
    assert "OKF claims need verification" in captured["report_text"]
    assert "saved_profile" not in captured
