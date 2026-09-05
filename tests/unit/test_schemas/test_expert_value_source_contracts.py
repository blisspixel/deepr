"""Published preparation schemas match runtime payloads and deny authority."""

import copy
import json
from pathlib import Path

import jsonschema
import pytest

from tests.unit.test_eval.test_expert_value_sources import Bundle

SCHEMA_DIR = Path(__file__).resolve().parents[3] / "docs" / "schemas"


def test_source_world_index_manifest_and_preflight_match_published_schemas(tmp_path):
    bundle = Bundle(tmp_path)
    for name, payload in [
        ("expert-value-source-index", bundle.index),
        ("expert-value-source-world", bundle.worlds[0]),
        ("expert-value-source-preflight", bundle.check()),
    ]:
        schema = json.loads((SCHEMA_DIR / f"{name}-v1.json").read_text())
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(schema).validate(payload)
        assert schema["x-deepr-linked-validator"]["schema_only_is_sufficient"] is False


@pytest.mark.parametrize(
    "field",
    [
        "execution_authorized",
        "run_ready",
        "semantic_quality_assessed",
        "historical_availability_independently_verified",
    ],
)
def test_source_preflight_schema_cannot_claim_review_or_execution_authority(tmp_path, field):
    schema = json.loads((SCHEMA_DIR / "expert-value-source-preflight-v1.json").read_text())
    payload = copy.deepcopy(Bundle(tmp_path).check())
    payload[field] = True
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(payload)
