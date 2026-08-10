"""`deepr expert status`: where an expert is in the loop, and why.

The state worth having is `failed` - the artifact exists and carries nothing.
Every prior view could only ask "does the file exist", and a brief holding zero
positions passes that. Profiling against one produced a standpoint about the
pipeline failing rather than about the subject.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from deepr.cli.commands.semantic.experts import expert


@pytest.fixture
def expert_home(tmp_path, monkeypatch):
    home = tmp_path / "experts"
    monkeypatch.setattr("deepr.cli.commands.semantic.expert_status.canonical_expert_dir", lambda n: home / n)
    return home


@pytest.fixture
def profile(monkeypatch):
    class FakeProfile:
        name = "Subject"

    class FakeStore:
        def load(self, name):
            return FakeProfile() if name == "Subject" else None

    monkeypatch.setattr("deepr.experts.profile.ExpertStore", FakeStore)
    return FakeProfile


def _build(home, *, sources=3, findings=10, grounded=8, positions=1, standpoint="I read this as X."):
    d = home / "Subject"
    (d / "corpus").mkdir(parents=True, exist_ok=True)
    (d / "corpus" / "index.jsonl").write_text("\n".join('{"x":1}' for _ in range(sources)), encoding="utf-8")
    (d / "study.json").write_text(
        json.dumps({"totals": {"findings": findings, "grounded_findings": grounded}}), encoding="utf-8"
    )
    (d / "brief.json").write_text(
        json.dumps({"positions": [{"question": f"Q{i}"} for i in range(positions)]}), encoding="utf-8"
    )
    if standpoint:
        (d / "profile_card.json").write_text(json.dumps({"standpoint": standpoint}), encoding="utf-8")
    return d


class TestItSeparatesFailedFromDone:
    def test_an_artifact_that_carries_nothing_reads_as_failed(self, profile, expert_home):
        """The exact case: a timed-out synthesis wrote a parseable, empty brief."""
        _build(expert_home, positions=0)

        r = CliRunner().invoke(expert, ["status", "Subject", "--json"])

        stages = {s["stage"]: s for s in json.loads(r.output)["stages"]}
        assert stages["brief"]["status"] == "failed"

    def test_a_real_artifact_reads_as_done(self, profile, expert_home):
        _build(expert_home)
        stages = {s["stage"]: s for s in json.loads(CliRunner().invoke(expert, ["status", "Subject", "--json"]).output)["stages"]}
        assert stages["brief"]["status"] == "done"

    def test_the_human_view_warns_about_failed_stages(self, profile, expert_home):
        _build(expert_home, positions=0)
        r = CliRunner().invoke(expert, ["status", "Subject"])
        assert "carries nothing" in r.output


class TestBlockedNamesTheFix:
    def test_an_empty_brief_blocks_the_profile_and_says_why(self, profile, expert_home):
        _build(expert_home, positions=0, standpoint="")

        r = CliRunner().invoke(expert, ["status", "Subject"])

        assert "holds no positions" in r.output
        assert "expert brief" in r.output

    def test_ungrounded_findings_block_the_brief(self, profile, expert_home):
        _build(expert_home, grounded=0, positions=0, standpoint="")
        r = CliRunner().invoke(expert, ["status", "Subject", "--json"])
        stages = {s["stage"]: s for s in json.loads(r.output)["stages"]}
        assert stages["brief"]["status"] == "blocked"


class TestWhatToDoNext:
    def test_a_failed_stage_outranks_a_ready_one(self, profile, expert_home):
        """Building on a stage that produced nothing is how corruption spreads."""
        _build(expert_home, positions=0, standpoint="")
        assert json.loads(CliRunner().invoke(expert, ["status", "Subject", "--json"]).output)["next"] == "brief"

    def test_a_complete_expert_has_nothing_next(self, profile, expert_home):
        d = _build(expert_home)
        (d / "graph").mkdir(exist_ok=True)
        (d / "graph" / "evidence.json").write_text(json.dumps({"stats": {"is_formed": True}}), encoding="utf-8")
        (d / "practice.json").write_text(json.dumps({"stats": {"live_pursuits": 2}}), encoding="utf-8")
        (d / "viva.json").write_text(json.dumps({"exchanges": [{"question": "Q"}]}), encoding="utf-8")

        assert json.loads(CliRunner().invoke(expert, ["status", "Subject", "--json"]).output)["next"] is None


class TestReadingArtifacts:
    def test_an_unparseable_artifact_is_treated_as_missing(self, profile, expert_home):
        """Treating a corrupt file as present is how corruption travels."""
        d = _build(expert_home)
        (d / "brief.json").write_text("{not json", encoding="utf-8")

        stages = {s["stage"]: s for s in json.loads(CliRunner().invoke(expert, ["status", "Subject", "--json"]).output)["stages"]}
        assert stages["profile"]["status"] == "blocked"

    def test_an_empty_expert_reports_acquire_as_the_next_step(self, profile, expert_home):
        (expert_home / "Subject").mkdir(parents=True, exist_ok=True)
        assert json.loads(CliRunner().invoke(expert, ["status", "Subject", "--json"]).output)["next"] == "acquire"

    def test_it_costs_nothing_and_says_so(self, profile, expert_home):
        _build(expert_home)
        assert json.loads(CliRunner().invoke(expert, ["status", "Subject", "--json"]).output)["cost_usd"] == 0.0

    def test_an_unknown_expert_exits_two(self, profile, expert_home):
        r = CliRunner().invoke(expert, ["status", "Nobody"])
        assert r.exit_code == 2
