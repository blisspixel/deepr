"""Regression tests for runtime data-root portability."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace


def _write_benchmark_fixture(root: Path, model_key: str) -> None:
    benchmarks = root / "benchmarks"
    benchmarks.mkdir(parents=True)
    (benchmarks / "benchmark_20260629_000000.json").write_text(
        json.dumps(
            {
                "rankings": [
                    {
                        "model_key": model_key,
                        "scores_by_type": {
                            "quick_lookup": 0.91,
                        },
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def test_eval_writers_default_under_data_dir(monkeypatch, tmp_path):
    """Saved eval artifacts follow DEEPR_DATA_DIR when no output_dir is given."""
    monkeypatch.setenv("DEEPR_DATA_DIR", str(tmp_path))

    from deepr.evals.consult import ConsultEvalOutcome, ConsultEvalReport, write_consult_eval_report
    from deepr.evals.local_compare import LocalComparisonReport, write_report
    from deepr.evals.local_context import LocalContextEvalReport, write_context_report

    consult_path = write_consult_eval_report(
        ConsultEvalReport(
            outcomes=(ConsultEvalOutcome(case_id="case", category="contract", passed=True),),
        )
    )
    local_path = write_report(
        LocalComparisonReport(prompt_set="agentic-loops", judge_model="judge", prompts=(), comparisons=())
    )
    context_path = write_context_report(
        LocalContextEvalReport(model="model", judge_model="judge", prompt_set="freshness", prompts=(), results=())
    )

    expected_root = tmp_path / "benchmarks"
    assert consult_path.parent == expected_root
    assert local_path.parent == expected_root
    assert context_path.parent == expected_root


def test_benchmark_artifact_helpers_default_under_data_dir(monkeypatch, tmp_path):
    """Reviewed local safety artifacts share the runtime benchmarks root."""
    monkeypatch.setenv("DEEPR_DATA_DIR", str(tmp_path))

    from deepr.experts.consult_quality import _eval_action, _review_action
    from deepr.experts.monitor_promotion import _write_eval_case_artifact
    from deepr.security.red_team import RedTeamReport, write_red_team_report

    expected_root = tmp_path / "benchmarks"
    red_team_path = write_red_team_report(RedTeamReport(outcomes=()))
    monitor_path = _write_eval_case_artifact({"proposal_id": "case-1"}, output_dir=None)
    review_preview = _review_action({"review_id": "review-1"}, apply=False, output_dir=None)
    eval_preview = _eval_action(
        profile=SimpleNamespace(name="expert"),
        review={
            "eligible_for_promotion": True,
            "review_id": "review-1",
            "review_status": "accepted",
            "mean_score": 0.91,
            "decision": "accept",
        },
        candidate={"trace_id": "trace-1", "eval_case": {"prompt": "p", "expected": "e"}},
        apply=False,
        output_dir=None,
    )

    assert red_team_path.parent == expected_root
    assert monitor_path.parent == expected_root
    assert review_preview["would_write"] == str(expected_root)
    assert eval_preview["would_write"] == str(expected_root)


def test_benchmark_readers_default_under_data_dir(monkeypatch, tmp_path):
    """Routers load benchmark rankings from DEEPR_DATA_DIR, not the repo CWD."""
    monkeypatch.setenv("DEEPR_DATA_DIR", str(tmp_path))

    from deepr.experts.router import ModelRouter
    from deepr.providers.registry import MODEL_CAPABILITIES
    from deepr.routing import auto_mode

    openai_model_key = next(model for model in MODEL_CAPABILITIES if model.startswith("openai/"))
    _write_benchmark_fixture(tmp_path, openai_model_key)

    auto_mode._rankings_cache = None
    auto_mode._rankings_mtime = 0.0
    auto_mode._rankings_check_ts = 0.0

    rankings = auto_mode._load_benchmark_rankings()
    openai_rankings = ModelRouter()._load_openai_benchmarks()

    assert rankings is not None
    assert rankings["quick_lookup"][0][0] == "openai"
    assert openai_rankings is not None
    assert openai_rankings["quick_lookup"][0][0] == openai_model_key.split("/", 1)[1]


def test_mcp_state_defaults_resolve_data_dir_at_construction(monkeypatch, tmp_path):
    """MCP state DB defaults are not frozen at module import time."""
    from deepr.mcp.security.output_verification import OutputVerifier
    from deepr.mcp.state.credential_manager import CredentialManager
    from deepr.mcp.state.persistence import JobPersistence
    from deepr.mcp.state.task_durability import TaskDurabilityManager

    first_root = tmp_path / "first"
    second_root = tmp_path / "second"

    monkeypatch.setenv("DEEPR_DATA_DIR", str(first_root))
    first = CredentialManager()
    try:
        assert first._db_path == first_root / "credentials.db"
    finally:
        first.close()

    monkeypatch.setenv("DEEPR_DATA_DIR", str(second_root))
    credential_manager = CredentialManager()
    output_verifier = OutputVerifier()
    job_persistence = JobPersistence()
    task_durability = TaskDurabilityManager()
    try:
        assert credential_manager._db_path == second_root / "credentials.db"
        assert output_verifier._db_path == second_root / "output_verification.db"
        assert job_persistence._db_path == second_root / "mcp_jobs.db"
        assert task_durability._db_path == second_root / "durable_tasks.db"
    finally:
        credential_manager.close()
        output_verifier.close()
        job_persistence.close()
        task_durability.close()


def test_runtime_data_path_keeps_repo_local_default(monkeypatch):
    """The helper preserves the documented CWD-local data default."""
    from deepr.config import runtime_data_path

    monkeypatch.delenv("DEEPR_DATA_DIR", raising=False)

    assert runtime_data_path("benchmarks") == Path("data") / "benchmarks"
