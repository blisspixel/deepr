"""Published schema checks for consult lifecycle events."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from deepr.experts.consult_lifecycle import ConsultLifecycle, load_consult_lifecycle_events

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "docs" / "schemas" / "consult-lifecycle-event-v1.json"


def _start(path: Path) -> ConsultLifecycle:
    return ConsultLifecycle.start(
        path=path,
        max_elapsed_seconds=120,
        capacity={
            "source": "local_owned",
            "backend": "local",
            "provider": "ollama",
            "model": "qwen3.6",
            "admission": "admitted",
            "live_metered_fallback": False,
        },
        bounds={
            "dispatch_scope": "council_work_item",
            "max_cost_usd": 2.0,
            "max_dispatches": 3,
            "max_output_tokens": 2048,
            "max_context_bytes": 32_768,
        },
        lineage={
            "operation": "one_shot",
            "question_hash": "d" * 64,
            "roster_hash": "e" * 64,
        },
    )


def test_published_schema_validates_started_heartbeat_resume_and_terminal_events(tmp_path: Path) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    path = tmp_path / "lifecycle.jsonl"
    lifecycle = _start(path)
    lifecycle.heartbeat(phase="perspectives")
    lifecycle.transition("waiting_capacity", phase="synthesis", reason_code="local_capacity_busy")
    resumed = ConsultLifecycle.resume(trace_id=lifecycle.trace_id, path=path)
    resumed.finish("completed", reason_code="trace_finalized")

    events = load_consult_lifecycle_events(trace_id=lifecycle.trace_id, path=path)
    for event in events:
        validator.validate(event)


def test_published_schema_validates_events_without_unmeasured_token_or_context_fields(tmp_path: Path) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    lifecycle = ConsultLifecycle.start(
        path=tmp_path / "minimal_lifecycle.jsonl",
        max_elapsed_seconds=120,
        capacity={
            "source": "local_owned",
            "backend": "local",
            "provider": "ollama",
            "model": "qwen3.6",
            "admission": "admitted",
            "live_metered_fallback": False,
        },
        bounds={
            "dispatch_scope": "council_work_item",
            "max_cost_usd": 0.0,
            "max_dispatches": 2,
        },
        lineage={
            "operation": "one_shot",
            "question_hash": "d" * 64,
            "roster_hash": "e" * 64,
        },
    )

    event = load_consult_lifecycle_events(path=lifecycle.path)[0]
    validator.validate(event)
    assert set(event["bounds"]) == {"dispatch_scope", "max_cost_usd", "max_dispatches"}
    assert set(event["progress"]) == {"cost_usd_observed", "dispatches_completed"}
    assert set(event["remaining"]) == {"cost_usd", "dispatches", "elapsed_ms"}


def test_published_schema_requires_optional_remaining_counter_to_match_its_bound(tmp_path: Path) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    event = load_consult_lifecycle_events(path=_start(tmp_path / "optional_bound.jsonl").path)[0]

    missing_remaining = copy.deepcopy(event)
    missing_remaining["remaining"].pop("output_tokens")
    with pytest.raises(ValidationError):
        validator.validate(missing_remaining)

    stray_observation = copy.deepcopy(event)
    stray_observation["bounds"].pop("max_output_tokens")
    stray_observation["remaining"].pop("output_tokens")
    stray_observation["progress"]["output_tokens_observed"] = 0
    with pytest.raises(ValidationError):
        validator.validate(stray_observation)


def test_published_schema_rejects_content_and_nonfinite_elapsed_fields(tmp_path: Path) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    event = load_consult_lifecycle_events(path=_start(tmp_path / "lifecycle.jsonl").path)[0]

    with_content = copy.deepcopy(event)
    with_content["answer"] = "Untrusted model output"
    with pytest.raises(ValidationError):
        validator.validate(with_content)

    nonfinite = copy.deepcopy(event)
    nonfinite["max_elapsed_seconds"] = float("inf")
    with pytest.raises(ValidationError):
        validator.validate(nonfinite)


def test_published_schema_matches_runtime_started_reason_contract(tmp_path: Path) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    event = load_consult_lifecycle_events(path=_start(tmp_path / "lifecycle.jsonl").path)[0]

    invalid_initial = copy.deepcopy(event)
    invalid_initial["reason_code"] = "bogus"
    with pytest.raises(ValidationError):
        validator.validate(invalid_initial)

    invalid_resume = copy.deepcopy(event)
    invalid_resume["sequence"] = 2
    invalid_resume["previous_state"] = "interrupted"
    invalid_resume["reason_code"] = None
    with pytest.raises(ValidationError):
        validator.validate(invalid_resume)


def test_published_schema_describes_checkpoint_elapsed_contract() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    description = schema["properties"]["max_elapsed_seconds"]["description"]

    assert "hard wall" not in description.lower()
    assert "lifecycle boundaries" in description
    assert "after synchronous durable I/O returns" in description


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("bounds", "max_cost_usd", -0.01),
        ("bounds", "max_cost_usd", float("inf")),
        ("progress", "cost_usd_observed", -0.01),
        ("progress", "cost_usd_observed", float("inf")),
        ("remaining", "cost_usd", -0.01),
        ("remaining", "cost_usd", float("inf")),
    ],
)
def test_published_schema_rejects_invalid_cost_numbers(tmp_path: Path, section: str, field: str, value: float) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    event = load_consult_lifecycle_events(path=_start(tmp_path / "cost_schema.jsonl").path)[0]
    event[section][field] = value

    with pytest.raises(ValidationError):
        validator.validate(event)
