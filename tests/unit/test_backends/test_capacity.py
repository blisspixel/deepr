"""Tests for deepr.backends.capacity - capacity-source detection ($0, no I/O).

Detection takes injectable probes (ollama, which, env), so these run with no
network and no real subprocess/PATH dependency.
"""

from __future__ import annotations

import json

from click.testing import CliRunner

from deepr.backends.capacity import (
    BackendKind,
    CapacitySource,
    CostModel,
    _key_is_set,
    detect_capacity,
    ollama_status,
)
from deepr.backends.quota_ledger import QuotaEventType, QuotaLedgerEvent, record_quota_event
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
        assert d["backend_id"] == ""
        assert d["marginal_cost"] == "$0 (local)"


class TestOllamaProbe:
    def test_dead_port_returns_false_not_raise(self):
        # No server here: must degrade to (False, detail), never raise.
        ok, detail = ollama_status("http://localhost:1", timeout=0.1)
        assert ok is False
        assert "not reachable" in detail


class TestAvailableLocalModels:
    def test_unreachable_returns_empty_not_raise(self):
        from deepr.backends.capacity import available_local_models

        assert available_local_models("http://localhost:1", timeout=0.1) == []


class TestPlanQuotaDetection:
    def test_copilot_and_cursor_detected(self):
        present = {"copilot", "cursor-agent"}
        sources = detect_capacity(
            ollama_probe=lambda: (False, ""),
            which=lambda exe: f"/usr/bin/{exe}" if exe in present else None,
            env={},
        )
        copilot = next(s for s in sources if s.name.startswith("Copilot"))
        cursor = next(s for s in sources if s.name.startswith("Cursor"))
        assert copilot.available and copilot.kind == BackendKind.PLAN_QUOTA
        assert cursor.available and cursor.kind == BackendKind.PLAN_QUOTA

    def test_kiro_uses_documented_executable_name(self):
        sources = detect_capacity(
            ollama_probe=lambda: (False, ""),
            which=lambda exe: "C:/bin/kiro-cli.exe" if exe == "kiro-cli" else None,
            env={},
        )
        kiro = next(s for s in sources if s.name.startswith("Kiro CLI"))
        assert kiro.available
        assert kiro.backend_id == "kiro-cli"


class TestCapacityCommand:
    def test_runs_and_lists_groups(self):
        result = CliRunner().invoke(capacity, [])
        assert result.exit_code == 0
        assert "Local" in result.output
        assert "Metered API" in result.output

    def test_json_output(self):
        result = CliRunner().invoke(capacity, ["--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert any(item["kind"] == "api_metered" for item in data)

    def test_json_probe_includes_local_probe_result(self, monkeypatch):
        from deepr.cli.commands import capacity as capacity_module

        async def fake_probe_local():
            return {"ok": False, "model": "too-large", "reply": "", "latency_ms": 12, "error": "not enough memory"}

        monkeypatch.setattr("deepr.backends.local.probe_local", fake_probe_local)
        monkeypatch.setattr(
            capacity_module,
            "detect_capacity",
            lambda: [
                CapacitySource(
                    "Ollama",
                    BackendKind.LOCAL,
                    CostModel.OWNED_HARDWARE,
                    True,
                    backend_id="ollama",
                )
            ],
        )
        monkeypatch.setattr(capacity_module, "summarize_quota_state", lambda: [])

        result = CliRunner().invoke(capacity, ["--probe", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["local_probe"]["ok"] is False
        assert data[0]["local_probe"]["error"] == "not enough memory"

    def test_json_output_includes_quota_state_when_observed(self, tmp_path):
        record_quota_event(
            QuotaLedgerEvent(
                backend_id="codex",
                event_type=QuotaEventType.EXHAUSTED,
                units_remaining=0,
                unit_name="compute_units",
                detail="test exhaustion",
            ),
            path=tmp_path / "cap" / "quota_ledger.jsonl",
        )
        result = CliRunner().invoke(
            capacity,
            ["--json"],
            env={"DEEPR_CAPACITY_DATA_DIR": str(tmp_path / "cap")},
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        codex = next(item for item in data if item["backend_id"] == "codex")
        assert codex["quota_state"]["exhausted"] is True
        assert codex["quota_states"][0]["exhausted"] is True
        assert codex["quota_state"]["detail"] == "test exhaustion"

    def test_json_output_includes_account_scoped_quota_states(self, tmp_path):
        cap = tmp_path / "cap"
        record_quota_event(
            QuotaLedgerEvent(
                backend_id="agy",
                account_id="personal",
                event_type=QuotaEventType.USAGE_OBSERVED,
                units_remaining=3,
                unit_name="compute_units",
            ),
            path=cap / "quota_ledger.jsonl",
        )
        result = CliRunner().invoke(capacity, ["--json"], env={"DEEPR_CAPACITY_DATA_DIR": str(cap)})
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        agy = next(item for item in data if item["backend_id"] == "agy")
        assert agy["quota_state"]["account_id"] == "personal"
        assert agy["quota_states"][0]["account_id"] == "personal"

    def test_text_output_includes_quota_summary_when_observed(self, tmp_path):
        record_quota_event(
            QuotaLedgerEvent(
                backend_id="kiro-cli",
                event_type=QuotaEventType.QUARANTINED,
                detail="overage state unknown",
            ),
            path=tmp_path / "cap" / "quota_ledger.jsonl",
        )
        result = CliRunner().invoke(capacity, [], env={"DEEPR_CAPACITY_DATA_DIR": str(tmp_path / "cap")})
        assert result.exit_code == 0, result.output
        assert "Observed quota state" in result.output
        assert "kiro-cli" in result.output
        assert "overage state unknown" in result.output


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
        assert json.loads(r.output) == []

    def test_admit_cancelled_without_yes(self, tmp_path):
        env = self._env(tmp_path)
        r = CliRunner().invoke(capacity, ["admit", "m", "--task-class", "sync"], input="n\n", env=env)
        assert r.exit_code == 0
        assert "Cancelled" in r.output
        r2 = CliRunner().invoke(capacity, ["admissions", "--json"], env=env)
        assert json.loads(r2.output) == []

    def test_revoke(self, tmp_path):
        runner = CliRunner()
        env = self._env(tmp_path)
        runner.invoke(capacity, ["admit", "m", "--task-class", "sync", "-y"], env=env)
        r = runner.invoke(capacity, ["revoke", "m", "--task-class", "sync"], env=env)
        assert r.exit_code == 0
        assert "Revoked" in r.output
        r2 = runner.invoke(capacity, ["admissions", "--json"], env=env)
        assert json.loads(r2.output) == []

    def test_revoke_nothing_to_revoke(self, tmp_path):
        r = CliRunner().invoke(capacity, ["revoke", "ghost", "--task-class", "sync"], env=self._env(tmp_path))
        assert r.exit_code == 0
        assert "Nothing to revoke" in r.output

    def test_task_class_required(self, tmp_path):
        r = CliRunner().invoke(capacity, ["admit", "m", "-y"], env=self._env(tmp_path))
        assert r.exit_code != 0
        assert "task-class" in r.output.lower()

    def test_admit_from_eval_uses_artifact_winner(self, tmp_path):
        artifact = self._local_eval_artifact(tmp_path)
        env = self._env(tmp_path)

        r = CliRunner().invoke(
            capacity,
            ["admit", "--from-eval", str(artifact), "--task-class", "sync", "-y"],
            env=env,
        )

        assert r.exit_code == 0, r.output
        assert "Admitted 'good-local' for 'sync'" in r.output
        r2 = CliRunner().invoke(capacity, ["admissions", "--json"], env=env)
        data = json.loads(r2.output)
        assert data[0]["model"] == "good-local"
        assert data[0]["score"] == 0.81
        assert "local eval agentic-loops" in data[0]["note"]

    def test_admit_from_eval_can_select_named_model(self, tmp_path):
        artifact = self._local_eval_artifact(tmp_path)
        env = self._env(tmp_path)

        r = CliRunner().invoke(
            capacity,
            ["admit", "weak-local", "--from-eval", str(artifact), "--task-class", "sync", "--min-score", "0.1", "-y"],
            env=env,
        )

        assert r.exit_code == 0, r.output
        r2 = CliRunner().invoke(capacity, ["admissions", "--json"], env=env)
        data = json.loads(r2.output)
        assert data[0]["model"] == "weak-local"
        assert data[0]["score"] == 0.2

    def test_admit_from_eval_latest_uses_default_benchmarks_dir(self, tmp_path, monkeypatch):
        artifact = self._local_eval_artifact(tmp_path)
        bench = tmp_path / "data" / "benchmarks"
        bench.mkdir(parents=True)
        artifact.replace(bench / "local_compare_20260618_120000.json")
        monkeypatch.chdir(tmp_path)
        env = self._env(tmp_path)

        r = CliRunner().invoke(
            capacity,
            ["admit", "--from-eval", "latest", "--task-class", "sync", "-y"],
            env=env,
        )

        assert r.exit_code == 0, r.output
        r2 = CliRunner().invoke(capacity, ["admissions", "--json"], env=env)
        data = json.loads(r2.output)
        assert data[0]["model"] == "good-local"

    def test_admit_from_eval_rejects_low_score(self, tmp_path):
        artifact = self._local_eval_artifact(tmp_path)

        r = CliRunner().invoke(
            capacity,
            ["admit", "weak-local", "--from-eval", str(artifact), "--task-class", "sync", "-y"],
            env=self._env(tmp_path),
        )

        assert r.exit_code != 0
        assert "below required minimum" in r.output

    def test_admit_requires_model_without_eval_artifact(self, tmp_path):
        r = CliRunner().invoke(capacity, ["admit", "--task-class", "sync", "-y"], env=self._env(tmp_path))

        assert r.exit_code != 0
        assert "MODEL is required" in r.output

    def test_admit_from_eval_rejects_manual_score(self, tmp_path):
        artifact = self._local_eval_artifact(tmp_path)

        r = CliRunner().invoke(
            capacity,
            ["admit", "--from-eval", str(artifact), "--task-class", "sync", "--score", "0.9", "-y"],
            env=self._env(tmp_path),
        )

        assert r.exit_code != 0
        assert "omit --score" in r.output

    def _local_eval_artifact(self, tmp_path):
        path = tmp_path / "local_compare.json"
        path.write_text(
            json.dumps(
                {
                    "methodology_version": "1.0",
                    "generated_at": "2026-06-18T00:00:00+00:00",
                    "prompt_set": "agentic-loops",
                    "judge_model": "judge-local",
                    "winner": "good-local",
                    "cost": 0.0,
                    "comparisons": [
                        {
                            "model": "good-local",
                            "average_score": 0.81,
                            "average_latency_ms": 22,
                            "cost": 0.0,
                            "prompt_results": [
                                {
                                    "prompt_id": "p1",
                                    "task_class": "agentic_loop",
                                    "answer": "bounded answer",
                                    "latency_ms": 22,
                                    "verdict": {"score": 0.81, "reason": "ok", "raw": "{}"},
                                    "error": "",
                                }
                            ],
                        },
                        {
                            "model": "weak-local",
                            "average_score": 0.2,
                            "average_latency_ms": 20,
                            "cost": 0.0,
                            "prompt_results": [
                                {
                                    "prompt_id": "p1",
                                    "task_class": "agentic_loop",
                                    "answer": "weak answer",
                                    "latency_ms": 20,
                                    "verdict": {"score": 0.2, "reason": "weak", "raw": "{}"},
                                    "error": "",
                                }
                            ],
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        return path
