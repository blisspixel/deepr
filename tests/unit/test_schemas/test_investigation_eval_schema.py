"""Published schema coverage for the frozen investigation evaluator."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from deepr.evals.investigation import run_investigation_eval


def test_investigation_eval_report_matches_published_schema() -> None:
    schema_path = Path(__file__).resolve().parents[3] / "docs" / "schemas" / "investigation-eval-v1.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    payload = run_investigation_eval().to_dict()

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)
