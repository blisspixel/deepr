"""Tests for root-confined expert-value artifact verification."""

from __future__ import annotations

import hashlib
import socket
from pathlib import Path
from typing import Any, cast

import pytest

from deepr.evals.expert_value import ExpertValueReview
from deepr.evals.expert_value_artifacts import (
    ArtifactVerificationError,
    iter_expert_value_artifact_bindings,
    verify_expert_value_artifacts,
)
from tests.unit.test_eval.test_expert_value import _blueprint, _review_payload


def _write_binding(
    root: Path,
    record: dict[str, Any],
    *,
    reference_field: str,
    hash_field: str,
    content: str,
) -> None:
    reference = str(record[reference_field])
    path = root / reference
    path.parent.mkdir(parents=True, exist_ok=True)
    data = content.encode("utf-8")
    path.write_bytes(data)
    record[hash_field] = hashlib.sha256(data).hexdigest()


def _materialized_review(tmp_path: Path) -> tuple[ExpertValueReview, Path]:
    blueprint = _blueprint(tmp_path / "experts")
    payload = cast(dict[str, Any], _review_payload(blueprint))
    root = tmp_path / "artifacts"

    for index, world in enumerate(payload["source_worlds"]):
        _write_binding(
            root,
            world,
            reference_field="manifest_ref",
            hash_field="manifest_sha256",
            content=f"source world {index}",
        )
    for index, arm in enumerate(payload["arm_configurations"]):
        _write_binding(
            root,
            arm,
            reference_field="run_policy_ref",
            hash_field="run_policy_sha256",
            content=f"arm policy {index}",
        )
    for index, trial in enumerate(payload["trials"]):
        _write_binding(
            root,
            trial,
            reference_field="run_artifact_ref",
            hash_field="run_artifact_sha256",
            content=f"run artifact {index}",
        )
        _write_binding(
            root,
            trial,
            reference_field="answer_artifact_ref",
            hash_field="answer_artifact_sha256",
            content=f"answer artifact {index}",
        )
    protocol = payload["protocol_attestation"]
    _write_binding(
        root,
        protocol,
        reference_field="review_assignment_ref",
        hash_field="review_assignment_sha256",
        content="frozen randomized assignment",
    )
    for case in payload["cases"]:
        outcome = case["observed_outcome"]
        if outcome is not None:
            outcome["outcome_record_ref"] = f"outcomes/{outcome['outcome_id']}.json"
            _write_binding(
                root,
                outcome,
                reference_field="outcome_record_ref",
                hash_field="outcome_record_sha256",
                content="immutable outcome record",
            )
    return ExpertValueReview.model_validate(payload), root


def _replace_reference(
    review: ExpertValueReview,
    *,
    reference: str,
    sha256: str,
) -> ExpertValueReview:
    payload = review.model_dump(mode="json")
    payload["source_worlds"][0]["manifest_ref"] = reference
    payload["source_worlds"][0]["manifest_sha256"] = sha256
    return ExpertValueReview.model_validate(payload)


def test_verifies_every_binding_without_network_or_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    review, root = _materialized_review(tmp_path)
    before = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}

    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("artifact verification must not open a network connection")

    monkeypatch.setattr(socket, "socket", fail_network)
    monkeypatch.setattr(socket, "create_connection", fail_network)
    result = verify_expert_value_artifacts(review, root)
    after = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
    expected_count = len(list(iter_expert_value_artifact_bindings(review)))

    assert result == {
        "mode": "local_filesystem_sha256",
        "digest_algorithm": "sha256",
        "reference_count": expected_count,
        "declared_unique_reference_count": expected_count,
        "verified_reference_count": expected_count,
        "verified_file_count": expected_count,
        "protocol_attested": True,
        "independently_verified": True,
        "all_matched": True,
        "root_confined": True,
        "network_access": False,
    }
    assert after == before


def test_rejects_digest_mismatch(tmp_path: Path) -> None:
    review, root = _materialized_review(tmp_path)
    (root / review.source_worlds[0].manifest_ref).write_text("changed", encoding="utf-8")

    with pytest.raises(ArtifactVerificationError, match="digest does not match"):
        verify_expert_value_artifacts(review, root)


def test_rejects_missing_file(tmp_path: Path) -> None:
    review, root = _materialized_review(tmp_path)
    (root / review.source_worlds[0].manifest_ref).unlink()

    with pytest.raises(ArtifactVerificationError, match="does not resolve"):
        verify_expert_value_artifacts(review, root)


@pytest.mark.parametrize("reference", ["../outside.json", "..\\outside.json"])
def test_rejects_parent_traversal_even_when_target_exists(tmp_path: Path, reference: str) -> None:
    review, root = _materialized_review(tmp_path)
    outside = tmp_path / "outside.json"
    outside.write_text("outside", encoding="utf-8")
    escaped = _replace_reference(
        review,
        reference=reference,
        sha256=hashlib.sha256(outside.read_bytes()).hexdigest(),
    )

    with pytest.raises(ArtifactVerificationError, match="parent traversal"):
        verify_expert_value_artifacts(escaped, root)


def test_rejects_absolute_uri_and_fragment_references(tmp_path: Path) -> None:
    review, root = _materialized_review(tmp_path)
    digest = "a" * 64
    invalid = (
        (str((tmp_path / "absolute.json").resolve()), "relative file reference"),
        ("https://example.test/artifact.json", "relative file reference|URI"),
        ("answers/result.md:alternate", "plain relative file reference"),
        ("outcomes/events.jsonl#event-1", "plain relative file reference"),
    )

    for reference, message in invalid:
        changed = _replace_reference(review, reference=reference, sha256=digest)
        with pytest.raises(ArtifactVerificationError, match=message):
            verify_expert_value_artifacts(changed, root)


def test_rejects_conflicting_digests_for_one_resolved_file(tmp_path: Path) -> None:
    review, root = _materialized_review(tmp_path)
    payload = review.model_dump(mode="json")
    payload["source_worlds"][1]["manifest_ref"] = payload["source_worlds"][0]["manifest_ref"]
    conflicting = ExpertValueReview.model_validate(payload)

    with pytest.raises(ArtifactVerificationError, match="conflicting declared"):
        verify_expert_value_artifacts(conflicting, root)
