"""Published schema checks for durable expert-conversation contracts."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, ValidationError

from deepr.evals.conversation import conversation_contract_fixtures, run_conversation_eval

SCHEMA_DIR = Path(__file__).resolve().parents[3] / "docs" / "schemas"

SCHEMA_BY_FIXTURE = {
    "conversation": "expert-conversation-v1.json",
    "turn": "expert-conversation-turn-v1.json",
    "event": "expert-conversation-event-v1.json",
    "context_snapshot": "expert-context-snapshot-v1.json",
    "error": "expert-conversation-error-v1.json",
}


def _validator(filename: str) -> Draft202012Validator:
    schema: dict[str, Any] = json.loads((SCHEMA_DIR / filename).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


@pytest.mark.parametrize(("fixture_name", "schema_name"), SCHEMA_BY_FIXTURE.items())
def test_published_conversation_contract_fixture_validates(fixture_name: str, schema_name: str) -> None:
    _validator(schema_name).validate(conversation_contract_fixtures()[fixture_name])


def test_published_conversation_eval_report_validates() -> None:
    _validator("conversation-eval-v1.json").validate(run_conversation_eval().to_dict())


def test_conversation_schema_rejects_terminal_active_turn_and_local_spend() -> None:
    validator = _validator("expert-conversation-v1.json")
    fixture = conversation_contract_fixtures()["conversation"]

    terminal_active = copy.deepcopy(fixture)
    terminal_active["state"] = "closed"
    terminal_active["current_turn_id"] = terminal_active["latest_turn_id"]
    with pytest.raises(ValidationError):
        validator.validate(terminal_active)

    local_spend = copy.deepcopy(fixture)
    local_spend["bounds"]["max_cost_usd"] = 0.01
    with pytest.raises(ValidationError):
        validator.validate(local_spend)


def test_conversation_schema_requires_deletion_timestamp() -> None:
    validator = _validator("expert-conversation-v1.json")
    fixture = conversation_contract_fixtures()["conversation"]
    fixture["retention"]["content_deleted"] = True

    with pytest.raises(ValidationError):
        validator.validate(fixture)


def test_turn_schema_rejects_unbounded_context_and_enacted_authority() -> None:
    validator = _validator("expert-conversation-turn-v1.json")
    fixture = conversation_contract_fixtures()["turn"]

    too_many_turns = copy.deepcopy(fixture)
    too_many_turns["context"]["recent_turn_ids"] = [f"turn_{index:016d}" for index in range(7)]
    with pytest.raises(ValidationError):
        validator.validate(too_many_turns)

    enacted = copy.deepcopy(fixture)
    enacted["artifact"]["decision_implications"][0]["authority"] = "enacted"
    with pytest.raises(ValidationError):
        validator.validate(enacted)

    wrong_status = copy.deepcopy(fixture)
    wrong_status["artifact"]["semantic_status"] = "input_required"
    with pytest.raises(ValidationError):
        validator.validate(wrong_status)

    duplicate_evidence = copy.deepcopy(fixture)
    duplicate_evidence["artifact"]["evidence"].append(duplicate_evidence["artifact"]["evidence"][0])
    with pytest.raises(ValidationError):
        validator.validate(duplicate_evidence)


def test_turn_schema_requires_artifact_for_completed_turn() -> None:
    validator = _validator("expert-conversation-turn-v1.json")
    fixture = conversation_contract_fixtures()["turn"]
    fixture["artifact"] = None

    with pytest.raises(ValidationError):
        validator.validate(fixture)

    fixture["artifact_available"] = False
    validator.validate(fixture)


def test_turn_schema_hides_deleted_request_content() -> None:
    validator = _validator("expert-conversation-turn-v1.json")
    fixture = conversation_contract_fixtures()["turn"]
    fixture["request"]["content_available"] = False

    with pytest.raises(ValidationError):
        validator.validate(fixture)

    fixture["request"]["content"] = None
    validator.validate(fixture)


def test_event_schema_forbids_raw_content_and_credentials() -> None:
    validator = _validator("expert-conversation-event-v1.json")
    fixture = conversation_contract_fixtures()["event"]

    for field in ("prompt", "answer", "api_key", "bearer_token"):
        invalid = copy.deepcopy(fixture)
        invalid[field] = "secret or content"
        with pytest.raises(ValidationError):
            validator.validate(invalid)


def test_deleted_snapshot_cannot_retain_packets() -> None:
    validator = _validator("expert-context-snapshot-v1.json")
    fixture = conversation_contract_fixtures()["context_snapshot"]
    fixture["content_available"] = False
    fixture["content_deleted_at"] = "2026-07-15T17:00:00+00:00"

    with pytest.raises(ValidationError):
        validator.validate(fixture)

    fixture["expert_snapshots"] = None
    validator.validate(fixture)


def test_error_schema_forbids_raw_exception_and_request_data() -> None:
    validator = _validator("expert-conversation-error-v1.json")
    fixture = conversation_contract_fixtures()["error"]

    fixture["error"]["raw_exception"] = "sqlite path and secret"
    with pytest.raises(ValidationError):
        validator.validate(fixture)
