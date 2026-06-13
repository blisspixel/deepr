"""Tests for deepr.backends.capacity - capacity-source detection ($0, no I/O).

Detection takes injectable probes (ollama, which, env), so these run with no
network and no real subprocess/PATH dependency.
"""

from __future__ import annotations

from click.testing import CliRunner

from deepr.backends.capacity import (
    BackendKind,
    CapacitySource,
    CostModel,
    _key_is_set,
    detect_capacity,
    ollama_status,
)
from deepr.cli.commands.capacity import capacity


class TestDetection:
    def test_detects_each_kind_from_stubs(self):
        sources = detect_capacity(
            ollama_probe=lambda: (True, "2 models"),
            which=lambda exe: "/usr/bin/claude" if exe == "claude" else None,
            env={"OPENAI_API_KEY": "sk-real-key-123"},
        )
        ollama = next(s for s in sources if s.kind == BackendKind.LOCAL)
        assert ollama.available and ollama.cost_model == CostModel.OWNED_HARDWARE

        claude = next(s for s in sources if s.name.startswith("Claude Code"))
        assert claude.available and claude.kind == BackendKind.PLAN_QUOTA
        assert not next(s for s in sources if s.name.startswith("Codex")).available

        openai = next(s for s in sources if s.name == "OpenAI")
        assert openai.available and openai.cost_model == CostModel.METERED
        assert not next(s for s in sources if s.name == "Gemini").available

    def test_cheapest_kind_listed_first(self):
        sources = detect_capacity(ollama_probe=lambda: (False, ""), which=lambda e: None, env={})
        kinds = [s.kind for s in sources]
        assert kinds.index(BackendKind.LOCAL) < kinds.index(BackendKind.PLAN_QUOTA)
        assert kinds.index(BackendKind.PLAN_QUOTA) < kinds.index(BackendKind.API_METERED)

    def test_marginal_cost_labels(self):
        local = CapacitySource("x", BackendKind.LOCAL, CostModel.OWNED_HARDWARE, True)
        metered = CapacitySource("y", BackendKind.API_METERED, CostModel.METERED, True)
        assert local.marginal_cost == "$0 (local)"
        assert metered.marginal_cost == "paid per call"

    def test_key_is_set_rejects_placeholder(self):
        assert _key_is_set("sk-real-key")
        assert not _key_is_set("your-openai-api-key")
        assert not _key_is_set(None)
        assert not _key_is_set("")

    def test_to_dict_shape(self):
        s = CapacitySource("Ollama", BackendKind.LOCAL, CostModel.OWNED_HARDWARE, True, "2 models")
        d = s.to_dict()
        assert d["kind"] == "local"
        assert d["cost_model"] == "owned_hardware"
        assert d["available"] is True
        assert d["marginal_cost"] == "$0 (local)"


class TestOllamaProbe:
    def test_dead_port_returns_false_not_raise(self):
        # No server here: must degrade to (False, detail), never raise.
        ok, detail = ollama_status("http://localhost:1", timeout=0.1)
        assert ok is False
        assert "not reachable" in detail


class TestCapacityCommand:
    def test_runs_and_lists_groups(self):
        result = CliRunner().invoke(capacity, [])
        assert result.exit_code == 0
        assert "Local" in result.output
        assert "Metered API" in result.output

    def test_json_output(self):
        result = CliRunner().invoke(capacity, ["--json"])
        assert result.exit_code == 0
        import json

        data = json.loads(result.output)
        assert isinstance(data, list)
        assert any(item["kind"] == "api_metered" for item in data)


class TestAdmissionCommands:
    def _env(self, tmp_path):
        return {"DEEPR_CAPACITY_DATA_DIR": str(tmp_path / "cap")}

    def test_admit_then_listed(self, tmp_path):
        runner = CliRunner()
        env = self._env(tmp_path)
        r = runner.invoke(capacity, ["admit", "llama3.1", "--task-class", "sync", "-y"], env=env)
        assert r.exit_code == 0, r.output
        assert "Admitted 'llama3.1' for 'sync'" in r.output

        r2 = runner.invoke(capacity, ["admissions"], env=env)
        assert r2.exit_code == 0
        assert "llama3.1" in r2.output and "sync" in r2.output

    def test_admissions_json_empty(self, tmp_path):
        r = CliRunner().invoke(capacity, ["admissions", "--json"], env=self._env(tmp_path))
        assert r.exit_code == 0
        import json

        assert json.loads(r.output) == []

    def test_admit_cancelled_without_yes(self, tmp_path):
        env = self._env(tmp_path)
        r = CliRunner().invoke(capacity, ["admit", "m", "--task-class", "sync"], input="n\n", env=env)
        assert r.exit_code == 0
        assert "Cancelled" in r.output
        r2 = CliRunner().invoke(capacity, ["admissions", "--json"], env=env)
        import json

        assert json.loads(r2.output) == []

    def test_revoke(self, tmp_path):
        runner = CliRunner()
        env = self._env(tmp_path)
        runner.invoke(capacity, ["admit", "m", "--task-class", "sync", "-y"], env=env)
        r = runner.invoke(capacity, ["revoke", "m", "--task-class", "sync"], env=env)
        assert r.exit_code == 0
        assert "Revoked" in r.output
        r2 = runner.invoke(capacity, ["admissions", "--json"], env=env)
        import json

        assert json.loads(r2.output) == []

    def test_revoke_nothing_to_revoke(self, tmp_path):
        r = CliRunner().invoke(capacity, ["revoke", "ghost", "--task-class", "sync"], env=self._env(tmp_path))
        assert r.exit_code == 0
        assert "Nothing to revoke" in r.output

    def test_task_class_required(self, tmp_path):
        r = CliRunner().invoke(capacity, ["admit", "m", "-y"], env=self._env(tmp_path))
        assert r.exit_code != 0
        assert "task-class" in r.output.lower()
