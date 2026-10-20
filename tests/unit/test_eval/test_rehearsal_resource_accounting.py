"""Failed preparation and missing usage remain visible without model calls."""

import json

import pytest

from deepr.evals.expert_value_rehearsal import _call_usage, _resources
from tests.unit.test_eval.test_expert_value_rehearsal import FakeLauncher, run


class TimedOutMaintenance(FakeLauncher):
    """One returned preparation call, then a timeout with a matching intent."""

    def __init__(self):
        super().__init__(lambda spec, _cwd: "fail" if spec["phase"] == "maintain" else None)

    def __call__(self, spec_path, env, cwd, timeout):
        code = super().__call__(spec_path, env, cwd, timeout)
        spec = json.loads(spec_path.read_bytes())
        if spec["phase"] == "maintain":
            request = f"x:{spec['worker_id']}:{spec['attempt_id']}:2"
            with (cwd / "out/calls.jsonl").open("a") as handle:
                handle.write(
                    json.dumps({"request_id": request, "status": "failed", "error_type": "ReadTimeout"}) + "\n"
                )
            with (cwd / "costs/cost_ledger.jsonl").open("a") as handle:
                handle.write(json.dumps({"request_id": request, "cost_usd": 0, "metadata": {}}) + "\n")
        return code


@pytest.mark.parametrize("counter", [None, True, -1, 0.5, "5"])
def test_unobserved_counter_is_not_a_zero_measurement(tmp_path, counter):
    path = tmp_path / "calls.jsonl"
    path.write_text(
        json.dumps({"status": "returned", "raw_response": {"prompt_eval_count": counter, "eval_count": 2}}) + "\n"
    )

    usage = _call_usage(path)

    assert usage["unknown_usage_calls"] == 1
    assert usage["prompt_tokens"] == 0  # Known subtotal only, not observed zero.
    assert usage["output_tokens"] == 2


def test_observed_zero_is_known_and_failed_call_is_unknown(tmp_path):
    path = tmp_path / "calls.jsonl"
    path.write_text(
        json.dumps({"status": "returned", "raw_response": {"prompt_eval_count": 0, "eval_count": 2}}) + "\n"
    )
    assert _call_usage(path)["unknown_usage_calls"] == 0
    path.write_text(
        "\n".join(
            json.dumps(row)
            for row in [
                {"status": "returned", "raw_response": {"prompt_eval_count": 0, "eval_count": 2}},
                {"status": "failed", "error_type": "ReadTimeout"},
            ]
        )
        + "\n"
    )

    usage = _call_usage(path)

    assert usage["calls"] == 2 and usage["returned"] == 1
    assert usage["unknown_usage_calls"] == 1
    assert usage["prompt_tokens"] == 0 and usage["output_tokens"] == 2


def test_failed_maintenance_is_visible_even_when_every_cell_answers(tmp_path):
    _rehearsal, summary = run(
        tmp_path, FakeLauncher(lambda spec, _cwd: "fail" if spec["phase"] == "maintain" else None)
    )

    assert summary["answered"] == summary["planned_cells"] == 8
    assert summary["failed"] == 0 and summary["status"] == "operationally_complete"
    assert summary["failed_workers"] == 1
    phase = summary["resources_by_phase"]["maintain"]
    assert phase["failed_workers"] == 1
    assert phase["returned_calls"] == 1
    assert phase["unknown_usage_calls"] == 0  # Failure after a recorded response.
    assert summary["resource_scope"] == "worker_only_reported_token_subtotals"
    assert summary["warmup_included"] is False


def test_legacy_worker_metadata_cannot_claim_complete_usage():
    result = _resources(
        [
            {
                "phase": "maintain",
                "status": "completed",
                "wall_seconds": 1,
                "usage": {"calls": 2, "returned": 1, "prompt_tokens": 5, "output_tokens": 2},
            }
        ]
    )

    assert result["maintain"]["unknown_usage_calls"] == 2
    assert result["maintain"]["known_prompt_tokens"] == 5
    assert result["maintain"]["known_output_tokens"] == 2


def test_timeout_usage_is_explicit_in_full_run_summary(tmp_path):
    _rehearsal, summary = run(tmp_path, TimedOutMaintenance())

    assert summary["ledger_reconciled"] is True
    assert summary["answered"] == 8 and summary["failed"] == 0
    assert summary["failed_workers"] == 1
    assert summary["unknown_usage_calls"] == 1
    phase = summary["resources_by_phase"]["maintain"]
    assert phase["calls"] == 2 and phase["returned_calls"] == 1
    assert phase["known_prompt_tokens"] == 5 and phase["known_output_tokens"] == 2
    assert phase["unknown_usage_calls"] == phase["failed_workers"] == 1
