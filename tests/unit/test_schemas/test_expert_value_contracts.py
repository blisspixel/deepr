"""Published schema tests for longitudinal expert-value review and report artifacts."""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from deepr.evals.expert_value import build_expert_value_report
from tests.unit.test_eval.test_expert_value import _blueprint, _review

jsonschema = pytest.importorskip("jsonschema")
Draft202012Validator = jsonschema.Draft202012Validator

SCHEMA_DIR = Path(__file__).resolve().parents[3] / "docs" / "schemas"


def _schema(name: str) -> dict[str, object]:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def test_review_and_report_validate_against_published_schemas(tmp_path: Path) -> None:
    blueprint = _blueprint(tmp_path)
    review = _review(blueprint)
    report = build_expert_value_report(review, blueprint, now=datetime(2026, 4, 4, tzinfo=UTC))
    review_schema = _schema("expert-value-review-v1.json")
    report_schema = _schema("expert-value-report-v1.json")

    Draft202012Validator.check_schema(review_schema)
    Draft202012Validator(review_schema).validate(review.model_dump(mode="json"))
    Draft202012Validator.check_schema(report_schema)
    Draft202012Validator(report_schema).validate(report)


def test_report_schema_rejects_an_aggregate_score_or_winner(tmp_path: Path) -> None:
    blueprint = _blueprint(tmp_path)
    report = build_expert_value_report(_review(blueprint), blueprint)
    report_schema = _schema("expert-value-report-v1.json")

    with_score = copy.deepcopy(report)
    with_score["score"] = 0.9
    with pytest.raises(jsonschema.ValidationError):
        Draft202012Validator(report_schema).validate(with_score)

    with_winner = copy.deepcopy(report)
    with_winner["winner"] = "maintained_expert"
    with pytest.raises(jsonschema.ValidationError):
        Draft202012Validator(report_schema).validate(with_winner)
