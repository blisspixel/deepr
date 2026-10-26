"""Offline structural fixtures, not evidence of useful or current advice."""

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from deepr.experts.preparation_contracts import (
    Assumption,
    CallerScope,
    Conflict,
    Implication,
    Interpretation,
    Omission,
    PackageCoordinate,
    PreparationEnvelope,
    PreparationLimits,
    PreparationPacket,
    PreparationRequest,
    PythonEnvironment,
    SourceObservation,
    canonical_bytes,
    freeze_packet,
    sha256,
)


def request_data():
    return {
        "schema_version": "deepr-python-preparation-request-v1",
        "enabled": True,
        "request_id": "synthetic_request_001",
        "environment": {"interpreter_version": "3.12.1", "platform": "fixture-platform"},
        "packages": [{"name": "Example_Project", "version": "1.2.0"}],
    }


def request():
    return PreparationRequest.from_json(json.dumps(request_data()).encode())


def packet():
    admitted = request()
    source = SourceObservation(
        observation_id="source_1",
        coordinate_id=admitted.packages[0].coordinate_id,
        source_class="pypi_release",
        requested_at=datetime(2026, 1, 1, tzinfo=UTC),
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
        status="ok",
        raw_sha256=sha256(b"raw fixture bytes"),
        parsed_sha256=sha256(b"parsed fixture bytes"),
        corpus_sha256=sha256(b"corpus fixture bytes"),
        limitations=("Version metadata does not establish advisory coverage.",),
    )
    return PreparationPacket(
        envelope=PreparationEnvelope(
            operation_id="operation_1",
            owner=CallerScope(namespace_sha256="a" * 64),
            request=admitted,
            question="Private synthetic placeholder question",
            expert_revision="b" * 64,
            stored_position_ids=("position1",),
        ),
        observations=(source,),
        interpretation=Interpretation(
            implications=(Implication(observation_ids=("source_1",), guidance="Review applicability."),)
        ),
        omissions=(Omission(reference_id=source.coordinate_id, reason="Index was not examined."),),
        attempts=1,
        stop_reason="partial",
    )


@pytest.mark.parametrize("field", ["delivered_context_sha256", "delivered_message_sha256"])
def test_final_delivery_identities_cannot_enter_frozen_packet(field):
    value = packet().model_dump(mode="json")
    value[field] = "a" * 64
    with pytest.raises(ValidationError, match="extra_forbidden"):
        PreparationPacket.model_validate_json(json.dumps(value))


@pytest.mark.parametrize("field", ["owner", "url", "credentials", "lockfile", "budget", "question", "packet_path"])
def test_public_request_rejects_authority_and_private_fields(field):
    value = request_data()
    value[field] = "synthetic"
    with pytest.raises(ValidationError):
        PreparationRequest.from_json(json.dumps(value).encode())


@pytest.mark.parametrize("replacement", [False, 1, "true", None])
def test_preparation_requires_explicit_true(replacement):
    value = request_data()
    value["enabled"] = replacement
    with pytest.raises(ValidationError):
        PreparationRequest.from_json(json.dumps(value).encode())


@pytest.mark.parametrize(
    "coordinate",
    [
        {"name": "https://example.invalid", "version": "1"},
        {"name": "package", "version": ">=1"},
        {"name": "../private", "version": "1"},
        {"name": "package", "version": "file:///private"},
        {"name": "package", "version": True},
    ],
)
def test_coordinates_refuse_noncoordinate_input(coordinate):
    with pytest.raises(ValidationError):
        PackageCoordinate.model_validate(coordinate)


def test_coordinate_coalescing_is_normalized_and_order_independent():
    value = request_data()
    value["packages"] += [{"name": "example-project", "version": "1.2.0"}]
    assert len(PreparationRequest.from_json(json.dumps(value).encode()).packages) == 1
    value["packages"][1]["version"] = "2.0"
    with pytest.raises(ValidationError, match="contradictory"):
        PreparationRequest.from_json(json.dumps(value).encode())


def test_public_input_and_id_bounds():
    with pytest.raises(ValueError, match="16 KiB"):
        PreparationRequest.from_json(b" " * 16385)
    value = request_data()
    value["request_id"] = "not/ascii/path_id"
    with pytest.raises(ValidationError):
        PreparationRequest.from_json(json.dumps(value).encode())


@pytest.mark.parametrize("bad", [True, 0, -1, 7, "6", 1.5])
def test_operation_limits_use_positive_strict_bounded_integers(bad):
    with pytest.raises(ValidationError):
        PreparationLimits(requests=bad)


def test_packet_freeze_is_deterministic_and_nested_state_is_immutable():
    original = packet()
    frozen = freeze_packet(original)
    assert frozen == freeze_packet(original)
    assert frozen.manifest.content_sha256 == sha256(canonical_bytes(original))
    assert frozen.manifest.review_markdown_sha256 == sha256(frozen.review_markdown)
    assert frozen.manifest.graph_sha256 == sha256(frozen.graph)
    assert frozen.manifest.content_sha256.encode() not in frozen.content
    assert original.observations[0].raw_sha256 != original.observations[0].parsed_sha256
    assert b"Index was not examined" in frozen.review_markdown
    assert b"source_1" in frozen.graph
    with pytest.raises(ValidationError):
        original.envelope.request.packages[0].name = "changed"
    with pytest.raises(ValidationError):
        frozen.content = b"changed"
    with pytest.raises(ValidationError, match="identity mismatch"):
        type(frozen)(
            content=b"changed", review_markdown=frozen.review_markdown, graph=frozen.graph, manifest=frozen.manifest
        )


def test_private_question_is_not_public_request_and_changes_content_identity():
    original = packet()
    assert "question" not in original.envelope.request.model_dump()
    value = original.model_dump(mode="json")
    value["envelope"]["question"] = "Different private placeholder"
    changed = PreparationPacket.model_validate_json(json.dumps(value))
    assert freeze_packet(original).manifest.content_sha256 != freeze_packet(changed).manifest.content_sha256
    assert original.envelope.question_sha256 != changed.envelope.question_sha256


@pytest.mark.parametrize("location", ["coordinate", "implication", "conflict", "omission"])
def test_packet_rejects_unknown_source_or_coordinate_references(location):
    value = packet().model_dump(mode="json")
    if location == "coordinate":
        value["observations"][0]["coordinate_id"] = "not_admitted"
    elif location == "implication":
        value["interpretation"]["implications"][0]["observation_ids"] = ["missing"]
    elif location == "conflict":
        value["interpretation"]["conflicts"] = [
            {"stored_position_id": "position", "observation_ids": ["missing"], "note": "Model interpretation"}
        ]
    else:
        value["omissions"][0]["reference_id"] = "missing"
    with pytest.raises(ValidationError):
        PreparationPacket.model_validate_json(json.dumps(value))


def test_observation_requires_aware_time_and_successful_bytes_identity():
    value = packet().observations[0].model_dump()
    value["observed_at"] = datetime(2026, 1, 1)
    with pytest.raises(ValidationError, match="timezone"):
        SourceObservation.model_validate(value)
    value = packet().observations[0].model_dump()
    value["raw_sha256"] = None
    with pytest.raises(ValidationError, match="identities"):
        SourceObservation.model_validate(value)


def test_adverse_metadata_is_allowed_without_advisory_coverage_claim():
    original = packet()
    coordinate = original.envelope.request.packages[0].coordinate_id
    assumption = Assumption(
        assumption_id="a1",
        coordinate_ids=(coordinate,),
        text="Could this release be yanked?",
        status="checked",
        reason="Interpret the retained metadata.",
    )
    conflict = Conflict(
        stored_position_id="position1",
        observation_ids=("source_1",),
        note="The metadata conflicts with the earlier recommendation.",
    )
    value = original.model_dump(mode="json")
    value["assumptions"] = [assumption.model_dump(mode="json")]
    value["interpretation"]["conflicts"] = [conflict.model_dump(mode="json")]
    result = PreparationPacket.model_validate_json(json.dumps(value))
    assert result.observations[0].advisory_coverage == "not_examined"
    assert result.interpretation.conflicts[0].note == conflict.note


def test_adverse_metadata_and_identities_survive_all_frozen_projections():
    value = packet().model_dump(mode="json")
    projection = canonical_bytes({"info": {"yanked": True}, "vulnerabilities": [{"id": "TEST-ADVERSE"}]})
    value["observations"][0].update(
        metadata_projection_json=projection.decode(), metadata_projection_sha256=sha256(projection)
    )
    frozen = freeze_packet(PreparationPacket.model_validate_json(json.dumps(value)))
    markdown = frozen.review_markdown.decode()
    graph = json.loads(frozen.graph)
    assert projection.decode() in markdown
    assert sha256(projection) in markdown
    assert "Comprehensive advisory coverage: not examined" in markdown
    assert graph["packet_sha256"] == frozen.manifest.content_sha256
    observation = graph["observations"][0]
    assert observation["metadata_projection_json"] == projection.decode()
    assert observation["raw_sha256"] == value["observations"][0]["raw_sha256"]


def test_environment_is_declared_not_inspected():
    with pytest.raises(ValidationError):
        PythonEnvironment(interpreter_version="3.12", platform="fixture", declaration="inspected")


def test_metadata_projection_identity_is_distinct_and_canonical():
    from datetime import UTC, datetime

    from deepr.experts.preparation_contracts import SourceObservation, canonical_bytes, sha256

    now = datetime.now(UTC)
    projection = canonical_bytes({"versions": ["1.0", "2.0"], "vulnerabilities": [{"id": "TEST-1"}]})
    fields = dict(
        observation_id="fixture_source",
        coordinate_id="fixture_coordinate",
        source_class="pypi_index",
        requested_at=now,
        observed_at=now,
        status="ok",
        raw_sha256="a" * 64,
        parsed_sha256="b" * 64,
    )
    result = SourceObservation(
        **fields, metadata_projection_json=projection.decode(), metadata_projection_sha256=sha256(projection)
    )
    assert result.raw_sha256 != result.parsed_sha256 != result.metadata_projection_sha256
    import pytest

    with pytest.raises(ValueError, match="canonical"):
        SourceObservation(
            **fields,
            metadata_projection_json=projection.decode() + " ",
            metadata_projection_sha256=sha256(projection + b" "),
        )
    with pytest.raises(ValueError, match="together"):
        SourceObservation(**fields, metadata_projection_json=projection.decode())


def test_comparison_status_does_not_default_to_no_change():
    from deepr.experts.preparation_contracts import Interpretation

    assert Interpretation().comparison_status == "unchecked"
    assert Interpretation(comparison_status="no_change").comparison_status == "no_change"
