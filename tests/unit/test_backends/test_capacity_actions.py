"""Tests for capacity next-action planning."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from click.testing import CliRunner

from deepr.backends.admission import record_admission
from deepr.backends.capacity import BackendKind, CapacitySource, CostModel
from deepr.backends.capacity_actions import CapacityNextAction, build_capacity_next_actions
from deepr.cli.commands.capacity import capacity

T0 = datetime(2026, 6, 18, tzinfo=UTC)


def _local_source(*, available: bool = True) -> CapacitySource:
    return CapacitySource(
        "Ollama",
        BackendKind.LOCAL,
        CostModel.OWNED_HARDWARE,
        available,
        backend_id="ollama",
    )


def _metered_source(*, available: bool = True) -> CapacitySource:
    return CapacitySource(
        "OpenAI",
        BackendKind.API_METERED,
        CostModel.METERED,
        available,
        backend_id="openai",
    )


def _artifact(bench, *, score: float = 0.82, model: str = "good-local"):
    bench.mkdir(parents=True, exist_ok=True)
    path = bench / "local_compare_20260618_120000.json"
    path.write_text(
        json.dumps(
            {
                "methodology_version": "1.0",
                "generated_at": "2026-06-18T00:00:00+00:00",
                "prompt_set": "agentic-loops",
                "judge_model": "judge-local",
                "winner": model,
                "cost": 0.0,
                "comparisons": [
                    {
                        "model": model,
                        "average_score": score,
                        "average_latency_ms": 12,
                        "cost": 0.0,
                        "prompt_results": [
                            {
                                "prompt_id": "p1",
                                "task_class": "sync",
                                "answer": "bounded answer",
                                "latency_ms": 12,
                                "verdict": {"score": score, "reason": "ok", "raw": "{}"},
                                "error": "",
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


class TestCapacityNextActions:
    def test_ready_when_scored_admission_is_available(self, tmp_path):
        p = tmp_path / "adm.jsonl"
        record_admission("good-local", "sync", score=0.82, now=T0, path=p)

        actions = build_capacity_next_actions(
            task_class="sync",
            now=T0,
            capacity_sources=[_local_source()],
            local_models=["good-local"],
            admissions_path=p,
            benchmarks_dir=tmp_path / "benchmarks",
        )

        assert [action.status for action in actions] == ["ready"]
        assert "Automatic local routing is ready" == actions[0].title
        assert "--fresh-context" in actions[0].command

    def test_scoreless_admission_prompts_eval(self, tmp_path):
        p = tmp_path / "adm.jsonl"
        record_admission("good-local", "sync", now=T0, path=p)

        actions = build_capacity_next_actions(
            task_class="sync",
            now=T0,
            capacity_sources=[_local_source()],
            local_models=["good-local"],
            admissions_path=p,
            benchmarks_dir=tmp_path / "benchmarks",
        )

        assert actions[0].status == "blocked"
        assert any(action.command.startswith("deepr eval local") for action in actions)

    def test_latest_eval_artifact_suggests_admission(self, tmp_path):
        p = tmp_path / "adm.jsonl"
        bench = tmp_path / "benchmarks"
        _artifact(bench, score=0.82, model="good-local")

        actions = build_capacity_next_actions(
            task_class="sync",
            now=T0,
            capacity_sources=[_local_source()],
            local_models=["good-local"],
            admissions_path=p,
            benchmarks_dir=bench,
        )

        admit = next(action for action in actions if action.status == "admit")
        assert "good-local" in admit.detail
        assert admit.command == "deepr capacity admit --from-eval latest --task-class sync"

    def test_latest_eval_winner_not_loaded_suggests_pull(self, tmp_path):
        bench = tmp_path / "benchmarks"
        _artifact(bench, score=0.82, model="good-local")

        actions = build_capacity_next_actions(
            task_class="sync",
            now=T0,
            capacity_sources=[_local_source()],
            local_models=["other-local"],
            admissions_path=tmp_path / "adm.jsonl",
            benchmarks_dir=bench,
        )

        setup = next(action for action in actions if action.title == "Pull the latest eval winner")
        assert setup.command == "ollama pull good-local"

    def test_low_latest_eval_artifact_prompts_refresh(self, tmp_path):
        bench = tmp_path / "benchmarks"
        _artifact(bench, score=0.4, model="weak-local")

        actions = build_capacity_next_actions(
            task_class="sync",
            now=T0,
            capacity_sources=[_local_source()],
            local_models=["weak-local"],
            admissions_path=tmp_path / "adm.jsonl",
            benchmarks_dir=bench,
        )

        refresh = next(action for action in actions if action.title == "Refresh the local eval")
        assert refresh.command.startswith("deepr eval local")

    def test_no_ollama_suggests_start_and_probe(self, tmp_path):
        actions = build_capacity_next_actions(
            task_class="sync",
            now=T0,
            capacity_sources=[_local_source(available=False)],
            local_models=[],
            admissions_path=tmp_path / "adm.jsonl",
            benchmarks_dir=tmp_path / "benchmarks",
        )

        commands = [action.command for action in actions]
        assert "ollama serve" in commands
        assert "deepr capacity --probe" in commands

    def test_metered_available_is_last_resort_action(self, tmp_path):
        actions = build_capacity_next_actions(
            task_class="sync",
            now=T0,
            capacity_sources=[_local_source(), _metered_source()],
            local_models=["good-local"],
            admissions_path=tmp_path / "adm.jsonl",
            benchmarks_dir=tmp_path / "benchmarks",
        )

        assert any(action.status == "fallback" and "--api" in action.command for action in actions)


class TestCapacityNextCommand:
    def test_prints_ranked_actions(self, monkeypatch):
        from deepr.backends import capacity_actions

        monkeypatch.setattr(
            capacity_actions,
            "build_capacity_next_actions",
            lambda **_: [
                CapacityNextAction(
                    1,
                    "ready",
                    "Automatic local routing is ready",
                    "local model clears quality floor",
                    'deepr expert sync "<expert>" --fresh-context -y',
                )
            ],
        )

        result = CliRunner().invoke(capacity, ["next", "--task-class", "sync"])

        assert result.exit_code == 0
        assert "Capacity next actions for task class: sync" in result.output
        assert "1. Automatic local routing is ready [ready]" in result.output

    def test_prints_json_actions(self, monkeypatch):
        from deepr.backends import capacity_actions

        monkeypatch.setattr(
            capacity_actions,
            "build_capacity_next_actions",
            lambda **_: [CapacityNextAction(1, "blocked", "Blocked", "reason")],
        )

        result = CliRunner().invoke(capacity, ["next", "--json"])

        assert result.exit_code == 0
        assert json.loads(result.output)[0]["status"] == "blocked"
