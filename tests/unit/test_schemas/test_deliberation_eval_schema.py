"""Published schema coverage for the frozen deliberation evaluator."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from deepr.evals.deliberation import run_deliberation_eval


def test_deliberation_eval_report_matches_published_schema() -> None:
    schema_path = Path(__file__).resolve().parents[3] / "docs" / "schemas" / "deliberation-eval-v1.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    payload = run_deliberation_eval().to_dict()

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)


def test_deliberation_schema_requires_capacity_and_fallback_contract_fields() -> None:
    schema_path = Path(__file__).resolve().parents[3] / "docs" / "schemas" / "deliberation-eval-v1.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)

    for field in ("capacity_mode", "fallback_policy"):
        payload = run_deliberation_eval().to_dict()
        payload["contract"].pop(field)

        assert list(validator.iter_errors(payload)), field
