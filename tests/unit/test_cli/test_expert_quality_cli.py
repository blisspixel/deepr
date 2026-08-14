"""CLI smoke tests for expert quality, improve, deepen-plan, and council-plan.

Offline and $0: no network, no model, no provider construction. These commands
shipped without CLI-level coverage, so the contracts pinned here are the ones a
host or script depends on: exit codes, JSON shape, and that nothing reaches a
paid path.
"""

import json

import pytest
from click.testing import CliRunner

from deepr.cli.commands.semantic.experts import expert


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def missing_expert(monkeypatch):
    """An expert store that resolves nothing, so no real store is touched."""

    class _Store:
        def load(self, name):
            return None

        def list_all(self):
            return []

    monkeypatch.setattr("deepr.experts.profile.ExpertStore", _Store)
    return _Store


class TestHelpSurfaces:
    @pytest.mark.parametrize("command", ["quality", "improve", "deepen-plan", "council-plan"])
    def test_help_exits_clean(self, runner, command):
        result = runner.invoke(expert, [command, "--help"])
        assert result.exit_code == 0, result.output
        assert result.output.strip()

    def test_improve_help_does_not_promise_a_flag_it_lacks(self, runner):
        """Help must not offer an --api escape hatch this command does not have.

        The original text said "Never metered without --api", which reads as an
        available flag and misdescribes where spend authority lives.
        """
        result = runner.invoke(expert, ["improve", "--help"])
        assert result.exit_code == 0
        assert "api" not in {p.name for p in expert.commands["improve"].params}
        assert "without --api" not in result.output
        # Naming the absent flag is fine; offering it as an option line is not.
        option_lines = [ln for ln in result.output.splitlines() if ln.strip().startswith("-")]
        assert not any("--api" in ln for ln in option_lines)

    def test_quality_help_states_it_is_structural(self, runner):
        result = runner.invoke(expert, ["quality", "--help"])
        assert "structural" in result.output.lower()


class TestUnknownExpert:
    @pytest.mark.parametrize("command", ["quality", "improve", "deepen-plan"])
    def test_unknown_expert_exits_two(self, runner, missing_expert, command):
        result = runner.invoke(expert, [command, "No Such Expert"])
        assert result.exit_code == 2, result.output


class TestCouncilPlanOffline:
    def test_scaffold_runs_without_model_or_network(self, runner):
        """No --local, no model: a structural scaffold, $0, exit 0."""
        result = runner.invoke(expert, ["council-plan", "Review a project roadmap"])
        assert result.exit_code == 0, result.output

    def test_json_payload_is_schema_shaped(self, runner):
        result = runner.invoke(expert, ["council-plan", "Review a project roadmap", "--json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["schema_version"] == "deepr-expert-council-plan-v1"
        assert payload["roles"]
        assert payload["axes_covered"]
        assert payload["cost_usd"] == 0.0

    def test_roles_span_multiple_axes(self, runner):
        """A roster of one axis is the failure the diversity gate exists to stop."""
        result = runner.invoke(expert, ["council-plan", "Review a project roadmap", "--json"])
        payload = json.loads(result.output)
        assert len({role["axis"] for role in payload["roles"]}) >= 4

    def test_missing_goal_and_file_exits_two(self, runner):
        result = runner.invoke(expert, ["council-plan"])
        assert result.exit_code == 2

    def test_from_file_reads_the_file(self, runner, tmp_path):
        doc = tmp_path / "readme.md"
        doc.write_text("A project that automates configuration.", encoding="utf-8")
        result = runner.invoke(expert, ["council-plan", "--from-file", str(doc), "--json"])
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["roles"]


class TestImproveExecute:
    def test_execute_skips_metered_discover_gaps(self, runner, monkeypatch):
        """Paid-gated discover-gaps must not be invoked as if it were local."""

        class FakeProfile:
            name = "Subject"
            domain = "d"

            def get_manifest(self):
                return type("M", (), {"domain": "d", "open_gap_count": 0})()

        class FakeStore:
            def load(self, name):
                return FakeProfile() if name == "Subject" else None

        class FakeBeliefStore:
            def __init__(self, name):
                self.beliefs = {}

        invoked: list[list[str]] = []

        class FakeRunner:
            def invoke(self, cli, argv):
                invoked.append(list(argv))
                return type("R", (), {"exit_code": 0, "output": "dry-run ok"})()

        monkeypatch.setattr("deepr.experts.profile.ExpertStore", FakeStore)
        monkeypatch.setattr("deepr.experts.beliefs.BeliefStore", FakeBeliefStore)
        monkeypatch.setattr("click.testing.CliRunner", FakeRunner)

        result = runner.invoke(expert, ["improve", "Subject", "--execute", "--json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        discover = next(step for step in payload["executed"] if step["step"] == "discover-gaps")
        assert discover["skipped"] is True
        assert "metered-gated" in discover["output_tail"]
        assert not any(argv[:2] == ["expert", "discover-gaps"] for argv in invoked)
        assert any("--dry-run" in argv for argv in invoked)


class TestNoPaidPath:
    def test_offline_commands_construct_no_provider(self, runner, monkeypatch):
        """None of these surfaces may reach a metered client."""
        called = []
        monkeypatch.setattr(
            "deepr.providers.create_provider",
            lambda *a, **k: called.append(a) or (_ for _ in ()).throw(AssertionError("provider constructed")),
            raising=False,
        )
        result = runner.invoke(expert, ["council-plan", "Some goal", "--json"])
        assert result.exit_code == 0
        assert called == []
