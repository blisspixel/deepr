"""Published schema coverage for epistemic-simulation Stage 0 artifacts."""

from __future__ import annotations

import importlib
import json
from datetime import UTC, datetime
from pathlib import Path

from jsonschema import Draft202012Validator
from pydantic import BaseModel

from deepr.evals.epistemic_simulation import (
    EpistemicSimulationCase,
    EpistemicSimulationCaseBundle,
    EpistemicSimulationEvalPayload,
    evaluate_epistemic_simulation,
)
from deepr.experts.epistemic_simulation_contract import ConsultContextPacket, EpistemicSimulation

ROOT = Path(__file__).resolve().parents[3]
SCHEMA_DIR = ROOT / "docs" / "schemas"
FIXTURE_PATH = ROOT / "tests" / "data" / "epistemic_simulation" / "acceptance-v1.json"


def _schema(name: str) -> dict[str, object]:
    payload = json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(payload)
    return payload


def _assert_generated_shape(name: str, model: type[BaseModel]) -> None:
    published = _schema(name)
    for metadata_key in ("$schema", "$id", "title", "description", "x-deepr-linked-validator"):
        published.pop(metadata_key)
    generated = model.model_json_schema(mode="validation")
    generated.pop("title", None)

    assert published == generated


def test_fixture_contract_and_context_match_published_schemas() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    Draft202012Validator(_schema("epistemic-simulation-v1.json")).validate(fixture["lens_snapshots"][0])
    Draft202012Validator(_schema("consult-context-v2.json")).validate(fixture["context_packets"][0])
    case_validator = Draft202012Validator(_schema("epistemic-simulation-case-v1.json"))
    for case in fixture["cases"]:
        case_validator.validate(case)
    Draft202012Validator(_schema("epistemic-simulation-case-bundle-v1.json")).validate(fixture)


def test_eval_report_matches_published_schema() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    bundle = EpistemicSimulationCaseBundle.model_validate(fixture)
    report = evaluate_epistemic_simulation(
        bundle,
        generated_at=datetime(2026, 7, 22, 12, 0, tzinfo=UTC),
    ).to_dict()

    Draft202012Validator(_schema("epistemic-simulation-eval-v1.json")).validate(report)


def test_published_schemas_match_executable_model_shapes() -> None:
    contracts = {
        "epistemic-simulation-v1.json": EpistemicSimulation,
        "consult-context-v2.json": ConsultContextPacket,
        "epistemic-simulation-case-v1.json": EpistemicSimulationCase,
        "epistemic-simulation-case-bundle-v1.json": EpistemicSimulationCaseBundle,
        "epistemic-simulation-eval-v1.json": EpistemicSimulationEvalPayload,
    }

    for name, model in contracts.items():
        schema = _schema(name)
        linked_validator = schema["x-deepr-linked-validator"]
        assert linked_validator["python"]
        assert linked_validator["schema_only_is_sufficient"] is False
        _assert_generated_shape(name, model)


def test_context_schema_metadata_names_and_invokes_authenticated_principal_input() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    metadata = _schema("consult-context-v2.json")["x-deepr-linked-validator"]
    assert "expected_principal_id from authenticated caller boundary" in metadata["requires"]

    module_name, attribute_name = metadata["python"].split(":", maxsplit=1)
    validator = getattr(importlib.import_module(module_name), attribute_name)
    lens = EpistemicSimulation.model_validate(fixture["lens_snapshots"][0])
    packet = ConsultContextPacket.model_validate(fixture["context_packets"][0])
    validator(
        lens,
        packet,
        expected_principal_id=fixture["contract"]["consumer_principal_id"],
    )
