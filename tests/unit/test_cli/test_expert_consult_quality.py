"""Tests for `deepr expert review-consult-quality`."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from deepr.cli.commands.semantic.expert_consult_quality import expert_review_consult_quality
from deepr.cli.main import cli
from deepr.core.contracts import Claim, ExpertManifest
from deepr.experts.consult_traces import record_consult_trace
from deepr.experts.profile import ExpertProfile


def _profile() -> ExpertProfile:
    profile = ExpertProfile(
        name="Consult Quality Expert",
        vector_store_id="vs-consult-quality",
        domain="consult quality",
        knowledge_cutoff_date=datetime(2026, 6, 27, tzinfo=UTC),
    )
    manifest = ExpertManifest(
        expert_name=profile.name,
        domain="consult quality",
        claims=[Claim.create("Consult quality reviews are human gated.", "consult quality", 0.9)],
    )
    profile.get_manifest = lambda: manifest  # type: ignore[method-assign]
    return profile


def _patch_store(profile):
    return patch(
        "deepr.cli.commands.semantic.expert_consult_quality.ExpertStore",
        return_value=MagicMock(load=MagicMock(return_value=profile)),
    )


def _write_failed_trace(path, profile: ExpertProfile):
    record_consult_trace(
        path=path,
        question="What should the consult council improve?",
        requested_experts=[profile.name],
        max_experts=3,
        budget=0.0,
        failure={"stage": "run_consult", "error_type": "RuntimeError", "message": "boom"},
        trace_id="consult_cli_quality",
    )


def _score_args() -> list[str]:
    return [
        "--score",
        "uses_expert_state=5",
        "--score",
        "surfaces_uncertainty=5",
        "--score",
        "preserves_dissent=5",
        "--score",
        "actionability=5",
        "--score",
        "grounded_when_factual=5",
        "--score",
        "original_thought=5",
    ]


def test_review_consult_quality_registered_in_expert_help():
    result = CliRunner().invoke(cli, ["expert", "review-consult-quality", "--help"])

    assert result.exit_code == 0
    assert "consult semantic-quality case" in result.output.lower()


def test_review_consult_quality_json_preview(tmp_path):
    profile = _profile()
    trace_path = tmp_path / "consult_traces.jsonl"
    _write_failed_trace(trace_path, profile)

    with _patch_store(profile):
        result = CliRunner().invoke(
            expert_review_consult_quality,
            [
                profile.name,
                "consult_cli_quality",
                *_score_args(),
                "--reviewer",
                "operator",
                "--decision",
                "accept",
                "--target",
                "eval",
                "--trace-path",
                str(trace_path),
                "--output-dir",
                str(tmp_path / "benchmarks"),
                "--json",
            ],
        )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == "deepr-consult-quality-review-v1"
    assert payload["status"] == "preview"
    assert payload["review_status"] == "accepted"
    assert not (tmp_path / "benchmarks").exists()


def test_review_consult_quality_missing_expert_exits_nonzero():
    with _patch_store(None):
        result = CliRunner().invoke(
            expert_review_consult_quality,
            ["Ghost Expert", "consult_missing", *_score_args(), "--reviewer", "operator", "--decision", "accept"],
        )

    assert result.exit_code != 0
    assert "not found" in result.output.lower()
