"""Run offline $0 TKG expert-value pilot and aggregate the report."""

from __future__ import annotations

from pathlib import Path

from deepr.evals.expert_value import build_expert_value_report, load_expert_value_review
from deepr.evals.expert_value_artifacts import verify_expert_value_artifacts
from deepr.evals.expert_value_pilot import run_pilot
from deepr.experts.blueprint import ExpertBlueprintStore
from deepr.utils.atomic_io import atomic_write_json

ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT / "artifacts"


def main() -> int:
    blueprint = ExpertBlueprintStore().load_latest("Temporal Knowledge Graphs")
    if blueprint is None:
        raise SystemExit("No operator-attested TKG blueprint")
    workbook = run_pilot(
        blueprint,
        ARTIFACTS,
        mode="offline_extract",
        review_set_id="tkg-value-2026-08-04",
    )
    review_path = ROOT / "expert-value-review.json"
    report_path = ROOT / "expert-value-report.json"
    review = load_expert_value_review(review_path)
    verification = verify_expert_value_artifacts(review, ARTIFACTS)
    report = build_expert_value_report(
        review,
        blueprint,
        artifact_verification=verification,
    )
    atomic_write_json(report_path, report, indent=2, fsync=True)
    print(f"workbook trials={len(workbook['trials'])}")
    print(f"wrote {review_path}")
    print(f"wrote {report_path}")
    for arm in report["arm_results"]:
        corr = arm["dimensions"]["correctness"]["mean_score"]
        false_support = arm["false_support"]["rate"]
        stale = arm["invalidated_belief_reuse"]["rate"]
        cost = arm["costs_usd"]["total_observed"]
        print(
            f"{arm['arm']}: correctness={corr} false_support={false_support} "
            f"stale_reuse={stale} cost={cost}"
        )
    av = report["artifact_verification"]
    print(
        f"artifact_verified={av['independently_verified']} "
        f"files={av['verified_file_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
