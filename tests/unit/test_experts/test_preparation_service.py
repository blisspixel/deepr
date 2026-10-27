"""Preparation service fixtures: fake model/source I/O, real private store/accounting."""

import asyncio
import json
import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from deepr.experts.investigation.ollama_backend import NativeOllamaInvestigationBackend
from deepr.experts.preparation_acquisition import AcquiredSource, AcquisitionCancelled, AcquisitionResult, RequestIntent
from deepr.experts.preparation_contracts import (
    CallerScope,
    PreparationPacket,
    PreparationRequest,
    canonical_bytes,
    sha256,
)
from deepr.experts.preparation_service import prepare_consultation
from deepr.experts.preparation_store import PreparationStore
from deepr.observability.cost_ledger import CostLedger

from .test_preparation_context import captured as captured


@pytest.mark.parametrize("phase", ["assumptions", "interpretation"])
def test_preparation_prompts_deliver_exact_response_contract(phase):
    from deepr.experts.preparation_contracts import PreparationLimits
    from deepr.experts.preparation_service import AssumptionPlan, PreparationAnalysis, _prompt

    prompt = _prompt(phase, {"question": "fixture"}, PreparationLimits())
    schema_text = prompt.split("===== RESPONSE JSON SCHEMA =====\n", 1)[1].split(
        "\n===== END RESPONSE JSON SCHEMA =====", 1
    )[0]
    response_type = AssumptionPlan if phase == "assumptions" else PreparationAnalysis
    assert json.loads(schema_text) == response_type.model_json_schema()
    assert "admitted coordinate_ids" not in prompt
    if phase == "assumptions":
        assert json.loads(schema_text)["$defs"]["PlannedAssumption"]["properties"]["status"]["enum"] == [
            "unchecked",
            "not_needed",
        ]


def test_live_misnamed_plan_fields_remain_refused_without_alias_or_salvage():
    from pydantic import ValidationError

    from deepr.experts.preparation_service import AssumptionPlan

    with pytest.raises(ValidationError):
        AssumptionPlan.model_validate(
            {
                "assumptions": [
                    {
                        "assumption_id": "a1",
                        "admitted_coordinate_ids": ["pkg_fixture"],
                        "text": "Fixture assumption",
                        "status": "unchecked",
                        "reason": "Fixture reason",
                    }
                ],
                "selected_coordinate_ids_to_check": ["pkg_fixture"],
            }
        )


@pytest.fixture
def service_fixture(tmp_path, monkeypatch, captured):
    capture, canonical_root = captured
    ledger = CostLedger(tmp_path / "costs" / "ledger.jsonl")
    monkeypatch.setattr("deepr.observability.local_attempts.CostLedger", lambda **kwargs: ledger)
    request = PreparationRequest.from_json(
        json.dumps(
            {
                "schema_version": "deepr-python-preparation-request-v1",
                "enabled": True,
                "request_id": "service_fixture_001",
                "environment": {"interpreter_version": "3.12", "platform": "synthetic"},
                "packages": [{"name": "fixture", "version": "1.0"}],
            }
        ).encode()
    )
    coordinate = request.packages[0]
    assumption = {
        "assumption_id": "a1",
        "coordinate_ids": [coordinate.coordinate_id],
        "text": "Does the declared version remain available?",
        "status": "unchecked",
        "reason": "Inspect the declared metadata.",
    }
    replies = [
        {"assumptions": [assumption], "selected_coordinate_ids": [coordinate.coordinate_id]},
        {
            "assumptions": [
                {**assumption, "status": "checked", "reason": "The supplied fixture returned matching metadata."}
            ],
            "interpretation": {
                "comparison_status": "no_change",
                "conflicts": [],
                "implications": [],
                "limitations": [],
            },
        },
    ]
    payloads = []

    async def get_json(url, timeout):
        if url.endswith("/api/status"):
            return {"cloud": {"disabled": True, "source": "both"}}
        return {
            "models": [
                {
                    "name": "fixture:local",
                    "model": "fixture:local",
                    "digest": "a" * 64,
                    "size": 1000000,
                    "details": {"format": "gguf"},
                }
            ]
        }

    async def post_json(url, payload, timeout):
        payloads.append(payload)
        return {
            "message": {"content": json.dumps(replies[len(payloads) - 1])},
            "done_reason": "stop",
            "prompt_eval_count": 100,
            "eval_count": 100,
        }

    backend = NativeOllamaInvestigationBackend(model="fixture:local", get_json=get_json, post_json=post_json)
    backend.last_attested_digest = "a" * 64
    store = PreparationStore(tmp_path / "private")
    owner = CallerScope(namespace_sha256="b" * 64)
    irreversible = AsyncMock()
    common = dict(
        request=request,
        question=capture.question,
        owner=owner,
        captured=capture,
        backend=backend,
        store=store,
        deadline=time.monotonic() + 210,
        trace_id="trace_fixture_001",
        on_irreversible_work=irreversible,
    )
    return common, replies, payloads, ledger, canonical_root


async def acquisition_fixture(coordinates, *, limits, reserve_intent):
    sources = []
    now = datetime.now(UTC).isoformat()
    for coordinate in coordinates:
        for kind in ("pypi_release", "pypi_index"):
            intent = RequestIntent(len(sources) + 1, coordinate.coordinate_id, kind)
            await reserve_intent(intent)
            data = (
                {
                    "info": {
                        "name": coordinate.name,
                        "version": coordinate.version,
                        "requires_python": ">=3.10",
                        "description": "omitted",
                        "yanked": True,
                        "yanked_reason": "Release summary fixture reason",
                    },
                    "urls": [
                        {
                            "filename": "fixture-1.0.tar.gz",
                            "yanked": False,
                            "yanked_reason": None,
                            "url": "https://unfetched.invalid/file",
                        }
                    ],
                    "vulnerabilities": [],
                }
                if kind == "pypi_release"
                else {
                    "name": coordinate.name,
                    "meta": {"api-version": "1.4"},
                    "versions": ["1.0", "2.0"],
                    "files": [
                        {
                            "filename": "fixture-1.0.tar.gz",
                            "yanked": "fixture reason",
                            "url": "https://unfetched.invalid/file",
                        }
                    ],
                }
            )
            raw = canonical_bytes(data)
            sources.append(AcquiredSource(intent, raw, sha256(raw), b"{}", now, now, 200, "ok", sha256(raw)))
    return AcquisitionResult(
        tuple(sources), len(sources), sum(len(source.raw) for source in sources), "complete", True, None, 0
    )


def tree(root):
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


@pytest.mark.asyncio
async def test_two_calls_private_evidence_and_canonical_invariance(service_fixture):
    common, _replies, payloads, ledger, root = service_fixture
    before = tree(root)
    outcome = await prepare_consultation(**common, acquirer=acquisition_fixture)
    assert outcome.answer_allowed and outcome.status == "complete"
    packet = PreparationPacket.model_validate_json(outcome.frozen.content)
    assert packet.attempts == 2 and packet.interpretation.comparison_status == "no_change"
    assert packet.assumptions[0].status == "checked"
    assert tree(root) == before and len(payloads) == 2
    assert all(payload["format"] == "json" and payload["options"]["num_predict"] == 1024 for payload in payloads)
    projections = [json.loads(item.metadata_projection_json) for item in packet.observations]
    assert projections[0]["yanked"] is True
    assert projections[0]["yanked_reason"] == "Release summary fixture reason"
    assert projections[0]["files"][0]["yanked"] is False
    assert projections[0]["files"][0]["yanked_reason"] is None
    assert packet.observations[0].metadata_projection_sha256 == sha256(canonical_bytes(projections[0]))
    assert projections[1]["versions"] == ["1.0", "2.0"]
    assert projections[1]["files"][0]["yanked"] == "fixture reason"
    # The simple index carries no vulnerability list; none is invented beside the release's own list.
    assert projections[0]["vulnerabilities"] == [] and "vulnerabilities" not in projections[1]
    assert all("vulnerability_metadata_provided" not in item for item in projections)
    assert projections[0]["omitted_source_keys"] == ["info.description", "files[].url"]
    assert projections[1]["listing_at_observation"]["highest_listed_version"] == "2.0"
    release_limits = packet.observations[0].limitations
    assert "2 source keys not projected (listed exactly in omitted_source_keys)" in release_limits[0]
    assert not any("Descriptive metadata omitted" in item for item in release_limits)
    assert "unfetched.invalid" not in json.dumps(projections)
    for observation in packet.observations:
        assert common["store"].read_source(common["owner"], outcome.claim.operation_id, observation.raw_sha256)
    assert common["store"].load(common["owner"], outcome.claim.operation_id) == outcome.frozen
    assert len(ledger.ledger_path.read_text().splitlines()) == 6
    duplicate = await prepare_consultation(
        **{**common, "trace_id": "a_new_transport_trace"},
        acquirer=AsyncMock(side_effect=AssertionError("duplicate dispatched")),
    )
    assert duplicate.status == "duplicate" and duplicate.frozen is None and not duplicate.answer_allowed
    assert len(payloads) == 2


@pytest.mark.asyncio
async def test_known_source_failure_stays_unchecked_and_allows_partial_advice(service_fixture):
    common, replies, payloads, _, _ = service_fixture
    replies[1]["assumptions"][0]["status"] = "unchecked"
    replies[1]["interpretation"]["comparison_status"] = "unchecked"

    async def unavailable(coordinates, *, limits, reserve_intent):
        complete = await acquisition_fixture(coordinates, limits=limits, reserve_intent=reserve_intent)
        sources = tuple(
            AcquiredSource(
                item.intent, b"", sha256(b""), b"{}", item.requested_at, item.observed_at, 503, "http_status", None
            )
            for item in complete.sources
        )
        return AcquisitionResult(sources, 2, 0, "partial", True, None, 0)

    outcome = await prepare_consultation(**common, acquirer=unavailable)
    packet = PreparationPacket.model_validate_json(outcome.frozen.content)
    assert outcome.answer_allowed and outcome.status == "partial"
    assert packet.assumptions[0].status == "unchecked" and packet.interpretation.comparison_status == "unchecked"
    assert all(item.status == "failed" for item in packet.observations)
    assert len(payloads) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["length", "unknown_usage", "malformed"])
async def test_bad_first_model_call_stops_acquisition_and_second_call(service_fixture, failure):
    common, _, payloads, _, _ = service_fixture
    native = common["backend"]
    original = native._post_json

    async def failed(url, payload, timeout):
        raw = await original(url, payload, timeout)
        if failure == "length":
            raw["done_reason"] = "length"
        elif failure == "unknown_usage":
            del raw["eval_count"]
        else:
            raw["message"]["content"] = '{"assumptions":['
        return raw

    native._post_json = failed
    acquirer = AsyncMock(side_effect=AssertionError("failed model must not acquire"))
    outcome = await prepare_consultation(**common, acquirer=acquirer)
    assert not outcome.answer_allowed and outcome.status == "failed" and len(payloads) == 1
    acquirer.assert_not_awaited()
    assert PreparationPacket.model_validate_json(outcome.frozen.content).stop_reason == "failed"


@pytest.mark.asyncio
async def test_oversized_adverse_projection_is_not_clipped_or_retried(service_fixture):
    common, _, payloads, _, _ = service_fixture

    async def adverse(coordinates, *, limits, reserve_intent):
        acquired = await acquisition_fixture(coordinates, limits=limits, reserve_intent=reserve_intent)
        first = acquired.sources[0]
        data = json.loads(first.raw)
        data["vulnerabilities"] = [{"id": "TEST-1", "details": "x" * 40000}]
        raw = canonical_bytes(data)
        replacement = AcquiredSource(
            first.intent, raw, sha256(raw), first.headers, first.requested_at, first.observed_at, 200, "ok", sha256(raw)
        )
        return AcquisitionResult(
            (replacement, acquired.sources[1]), 2, len(raw) + len(acquired.sources[1].raw), "complete", True, None, 0
        )

    outcome = await prepare_consultation(**common, acquirer=adverse)
    assert not outcome.answer_allowed and outcome.status == "failed" and len(payloads) == 1
    packet = PreparationPacket.model_validate_json(outcome.frozen.content)
    assert len(packet.observations) == 2
    raw = common["store"].read_source(common["owner"], outcome.claim.operation_id, packet.observations[0].raw_sha256)
    assert len(json.loads(raw)["vulnerabilities"][0]["details"]) == 40000
    assert packet.observations[0].metadata_projection_json is None


@pytest.mark.asyncio
async def test_model_cancellation_retains_consumed_attempt_and_no_fallback(service_fixture):
    common, _, _, _, _ = service_fixture

    async def cancelled(*args):
        raise asyncio.CancelledError()

    common["backend"]._post_json = cancelled
    with pytest.raises(asyncio.CancelledError):
        await prepare_consultation(**common, acquirer=AsyncMock(side_effect=AssertionError("cancelled work acquired")))
    duplicate = await prepare_consultation(**common, acquirer=acquisition_fixture)
    assert duplicate.claim.duplicate and duplicate.frozen is None and not duplicate.answer_allowed


@pytest.mark.asyncio
async def test_unconfirmed_acquisition_stops_interpretation(service_fixture):
    common, _, payloads, _, _ = service_fixture

    async def ambiguous(coordinates, *, limits, reserve_intent):
        acquired = await acquisition_fixture(coordinates, limits=limits, reserve_intent=reserve_intent)
        return AcquisitionResult(acquired.sources, 2, acquired.decoded_bytes, "failed", False, None, 4096)

    outcome = await prepare_consultation(**common, acquirer=ambiguous)
    assert not outcome.answer_allowed and outcome.status == "failed" and len(payloads) == 1
    state = common["store"]._read_json(
        common["store"].root / common["owner"].namespace_sha256 / outcome.claim.operation_id / "state.json"
    )
    assert state["acquisition_ambiguous"] is True


@pytest.mark.asyncio
async def test_reported_output_over_ceiling_is_not_another_allowance(service_fixture):
    common, _, payloads, _, _ = service_fixture
    native = common["backend"]
    original = native._post_json

    async def excess(*args):
        raw = await original(*args)
        raw["eval_count"] = 1025
        return raw

    native._post_json = excess
    source = AsyncMock(side_effect=AssertionError("over-bound model continued"))
    outcome = await prepare_consultation(**common, acquirer=source)
    assert not outcome.answer_allowed and len(payloads) == 1
    source.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancellation_carries_safe_operation_reference(service_fixture):
    common, _, _, _, _ = service_fixture

    async def cancelled(*args):
        raise asyncio.CancelledError()

    common["backend"]._post_json = cancelled
    with pytest.raises(asyncio.CancelledError) as caught:
        await prepare_consultation(**common, acquirer=acquisition_fixture)
    reference = caught.value.preparation_reference
    assert reference["owner_sha256"] == common["owner"].namespace_sha256
    assert reference["operation_id"].startswith("op_")
    assert "question" not in reference and "messages" not in reference


@pytest.mark.asyncio
@pytest.mark.parametrize("broken_write", ["settle_model_call", "complete"])
async def test_cancelled_model_preserves_cancellation_when_private_settlement_fails(
    service_fixture, monkeypatch, broken_write
):
    common, _, payloads, _, _ = service_fixture

    async def cancelled(*args):
        raise asyncio.CancelledError("original cancellation")

    def broken(*args, **kwargs):
        raise OSError("private storage details")

    common["backend"]._post_json = cancelled
    monkeypatch.setattr(common["store"], broken_write, broken)
    source = AsyncMock(side_effect=AssertionError("cancelled work acquired"))
    with pytest.raises(asyncio.CancelledError, match="original cancellation") as caught:
        await prepare_consultation(**common, acquirer=source)
    assert caught.value.preparation_persistence_unsettled is True
    assert caught.value.preparation_reference["operation_id"].startswith("op_")
    assert "private storage details" not in str(caught.value.__notes__)
    source.assert_not_awaited()
    assert not payloads
    duplicate = await prepare_consultation(**common, acquirer=source)
    assert duplicate.claim.duplicate and not duplicate.answer_allowed


@pytest.mark.asyncio
async def test_acquisition_cancellation_survives_receipt_failure(service_fixture, monkeypatch):
    common, _, payloads, _, _ = service_fixture
    terminal = AcquisitionResult((), 0, 0, "cancelled", True, None, 0)
    cancellation = AcquisitionCancelled(terminal)

    def broken(*args, **kwargs):
        raise OSError("private storage details")

    monkeypatch.setattr(common["store"], "settle_acquisition", broken)
    with pytest.raises(AcquisitionCancelled) as caught:
        await prepare_consultation(**common, acquirer=AsyncMock(side_effect=cancellation))
    assert caught.value is cancellation and caught.value.preparation_persistence_unsettled
    assert "private storage details" not in str(caught.value.__notes__)
    assert len(payloads) == 1


@pytest.mark.asyncio
async def test_adapter_captures_once_and_retains_final_receipts_privately(service_fixture, monkeypatch):
    from types import SimpleNamespace

    from deepr.experts.preparation_context import preparation_delivery
    from deepr.experts.preparation_service import PreparationAdmission, prepare_for_transaction

    common, _, payloads, _, _ = service_fixture
    captures = []

    def capture_once(question, name):
        captures.append((question, name))
        return common["captured"]

    monkeypatch.setattr("deepr.experts.preparation_service.capture_formed_context", capture_once)
    backend = SimpleNamespace(provider="local", model=common["backend"].model, client=common["backend"])
    admitted = PreparationAdmission(common["request"], common["owner"], common["store"].root)
    transaction = await prepare_for_transaction(
        admitted,
        question=common["question"],
        expert_name=common["captured"].expert_name,
        backend=backend,
        deadline=common["deadline"],
        trace_id=common["trace_id"],
        on_irreversible_work=common["on_irreversible_work"],
        acquirer=acquisition_fixture,
    )
    assert len(captures) == 1 and transaction.prepared.capture is common["captured"]
    assert (
        transaction.reference["capture_sha256"]
        and transaction.reference["owner_sha256"] == common["owner"].namespace_sha256
    )
    assert "question" not in transaction.reference
    before = transaction.outcome.frozen.content
    user = transaction.prepared.mandatory_text() + "Synthetic final question"
    intent = preparation_delivery(transaction.prepared, "synthetic system", user, "", status="dispatch_intent")
    await transaction.delivery_callback(intent)
    complete = preparation_delivery(
        transaction.prepared, "synthetic system", user, "synthetic answer", status="completed"
    )
    await transaction.delivery_callback(complete)
    assert transaction.outcome.frozen.content == before and len(payloads) == 2
    directory = common["store"].root / common["owner"].namespace_sha256 / transaction.outcome.claim.operation_id
    events = [json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()]
    deliveries = [event for event in events if event["kind"] == "delivery"]
    assert [event["status"] for event in deliveries] == ["dispatch_intent", "completed"]
    assert deliveries[0]["answer_sha256"] is None
    assert deliveries[1]["answer_sha256"] == sha256(b"synthetic answer")
    assert sha256((directory / "capture.json").read_bytes()) == transaction.reference["capture_sha256"]


@pytest.mark.asyncio
async def test_invalid_request_is_refused_before_native_attestation(service_fixture):
    common, _, _, _, _ = service_fixture
    proof = AsyncMock(side_effect=AssertionError("malformed admission probed native runtime"))
    common["backend"]._get_json = proof
    request = common["request"].model_copy(update={"enabled": False})
    with pytest.raises(ValueError):
        await prepare_consultation(**{**common, "request": request}, acquirer=acquisition_fixture)
    proof.assert_not_awaited()
    assert not list(common["store"].root.rglob("envelope.json"))


@pytest.mark.parametrize("summary", [{}, {"yanked": None, "yanked_reason": None}])
def test_release_projection_preserves_absent_and_null_summary_fields(summary):
    from deepr.experts.preparation_service import _projection

    coordinate = PreparationRequest.from_json(
        json.dumps(
            {
                "schema_version": "deepr-python-preparation-request-v1",
                "enabled": True,
                "request_id": "summary_fixture_001",
                "environment": {"interpreter_version": "3.12", "platform": "synthetic"},
                "packages": [{"name": "fixture", "version": "1.0"}],
            }
        ).encode()
    ).packages[0]
    raw = canonical_bytes({"info": {"name": "fixture", "version": "1.0", **summary}, "urls": []})
    now = datetime.now(UTC).isoformat()
    source = AcquiredSource(
        RequestIntent(1, coordinate.coordinate_id, "pypi_release"),
        raw,
        sha256(raw),
        b"{}",
        now,
        now,
        200,
        "ok",
        sha256(raw),
    )
    projection = json.loads(_projection(source, coordinate).text)
    assert {key: projection[key] for key in ("yanked", "yanked_reason") if key in projection} == summary
    # Absent source fields stay absent and are named; nothing is defaulted to [] or null.
    for key in ("vulnerabilities", "project-status", "requires_python"):
        assert key not in projection
    assert set(projection["fields_absent_in_source"]) == {
        "info.requires_python",
        "vulnerabilities",
        "project-status",
        *(f"info.{key}" for key in ("yanked", "yanked_reason") if key not in summary),
    }
    assert projection["files"] == []


@pytest.mark.asyncio
async def test_adapter_creates_missing_configured_parent_after_capture(service_fixture, monkeypatch):
    from types import SimpleNamespace

    from deepr.experts.preparation_service import PreparationAdmission, prepare_for_transaction

    common, _, _, _, _ = service_fixture
    root = common["store"].root.parent / "missing_config" / "runtime" / "preparation"

    def capture(question, expert_name):
        assert not root.parent.exists()
        return common["captured"]

    monkeypatch.setattr("deepr.experts.preparation_service.capture_formed_context", capture)
    monkeypatch.setattr(
        "deepr.experts.preparation_service.prepare_consultation",
        AsyncMock(return_value=SimpleNamespace(answer_allowed=False, frozen=None)),
    )
    result = await prepare_for_transaction(
        PreparationAdmission(common["request"], common["owner"], root),
        question=common["question"],
        expert_name=common["captured"].expert_name,
        backend=SimpleNamespace(provider="local", client=common["backend"], model=common["backend"].model),
        deadline=time.monotonic() + 210,
        trace_id="fixture",
        on_irreversible_work=AsyncMock(),
    )
    assert root.is_dir() and not result.outcome.answer_allowed


def test_configured_parent_refuses_link_before_outside_writes(tmp_path):
    from deepr.experts.preparation_service import _prepare_configured_parent
    from deepr.experts.preparation_store import StoreProtectionError

    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "linked"
    if __import__("sys").platform == "win32":
        import subprocess

        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], check=True, capture_output=True)
    else:
        link.symlink_to(outside, target_is_directory=True)
    try:
        with pytest.raises(StoreProtectionError):
            _prepare_configured_parent(link / "missing" / "preparation")
        assert list(outside.iterdir()) == []
    finally:
        link.rmdir() if __import__("sys").platform == "win32" else link.unlink()


def _coordinate(version="1.0"):
    return PreparationRequest.from_json(
        json.dumps(
            {
                "schema_version": "deepr-python-preparation-request-v1",
                "enabled": True,
                "request_id": "projection_fixture_001",
                "environment": {"interpreter_version": "3.12", "platform": "synthetic"},
                "packages": [{"name": "fixture", "version": version}],
            }
        ).encode()
    ).packages[0]


def _source(kind, data, coordinate, observed_at="2026-10-27T12:00:00+00:00"):
    raw = canonical_bytes(data)
    intent = RequestIntent(1 if kind == "pypi_release" else 2, coordinate.coordinate_id, kind)
    return AcquiredSource(intent, raw, sha256(raw), b"{}", observed_at, observed_at, 200, "ok", sha256(raw))


def _index_file(name, *, yanked=False):
    return {
        "filename": name,
        "url": "https://unfetched.invalid/" + name,
        "hashes": {"sha256": "1" * 64},
        "core-metadata": {"sha256": "2" * 64},
        "requires-python": ">=3.9",
        "upload-time": "2026-01-02T03:04:05.000000Z",
        "yanked": yanked,
        "size": 10,
    }


def test_index_projection_records_listing_at_observation_without_inventing_fields():
    from deepr.experts.preparation_service import _LISTING_LABEL, _projection

    coordinate = _coordinate("1.9")
    data = {
        "name": "fixture",
        "meta": {"api-version": "1.4", "_last-serial": 7},
        "versions": ["1.0", "1.10", "1.9", "2.0rc1", "not a version"],
        "files": [
            _index_file("fixture-1.9-py3-none-any.whl"),
            _index_file("fixture-1.9.tar.gz", yanked="broken sdist"),
            _index_file("fixture-1.10.tar.gz"),
            _index_file("unparseable.zip"),
        ],
        "alternate-locations": [],
    }
    projection_result = _projection(_source("pypi_index", data, coordinate), coordinate)
    projection = json.loads(projection_result.text)
    listing = projection["listing_at_observation"]
    # PEP 440 ordering, not lexical order; prereleases are listed identities too.
    assert listing == {
        "label": _LISTING_LABEL,
        "observed_at": "2026-10-27T12:00:00+00:00",
        "basis": "versions",
        "listed_version_count": 4,
        "unparsed_listed_versions": 1,
        "highest_listed_version": "2.0rc1",
        "target_listed": True,
        "target_files": [
            {"filename": "fixture-1.9-py3-none-any.whl", "upload-time": "2026-01-02T03:04:05.000000Z", "yanked": False},
            {"filename": "fixture-1.9.tar.gz", "upload-time": "2026-01-02T03:04:05.000000Z", "yanked": "broken sdist"},
        ],
    }
    assert [item["filename"] for item in projection["files"]] == [
        "fixture-1.9-py3-none-any.whl",
        "fixture-1.9.tar.gz",
    ]
    assert "vulnerabilities" not in projection and "project-status" not in projection
    assert projection["fields_absent_in_source"] == ["project-status"]
    assert projection["omitted_source_keys"] == ["alternate-locations", "files[].url"]
    assert "unfetched.invalid" not in projection_result.text
    semantics = projection["field_semantics"]
    assert "archive bytes named by filename" in semantics["files[].hashes"]
    assert "separate core metadata file" in semantics["files[].core-metadata"]
    assert "not an install, import or runtime test" in semantics["files[].requires-python"]
    assert "vulnerabilities" not in semantics
    assert any("1 other-version files and 1 unparsed" in item for item in projection_result.omitted)
    assert any(item.startswith("applicable_versions names only the target") for item in projection_result.omitted)


def test_index_projection_without_versions_lists_from_file_names_and_target_absence():
    from deepr.experts.preparation_service import _projection

    coordinate = _coordinate("3.0")
    data = {"name": "fixture", "meta": {"api-version": "1.0"}, "files": [_index_file("fixture-2.0.tar.gz")]}
    result = _projection(_source("pypi_index", data, coordinate), coordinate)
    projection = json.loads(result.text)
    listing = projection["listing_at_observation"]
    assert listing["basis"] == "file_names" and listing["highest_listed_version"] == "2.0"
    assert listing["target_listed"] is False and listing["target_files"] == []
    assert projection["fields_absent_in_source"] == ["versions", "project-status"]
    assert any("versions inventory absent" in item for item in result.omitted)


def test_projection_fixed_semantics_stay_inside_no_clipping_limit():
    from deepr.experts.preparation_service import _FIELD_SEMANTICS, _MAX_PROJECTION_CHARS, _projection

    coordinate = _coordinate()
    release_file = {
        "comment_text": "",
        "digests": {"blake2b_256": "3" * 64, "md5": "4" * 32, "sha256": "5" * 64},
        "downloads": -1,
        "filename": "fixture-1.0-py3-none-any.whl",
        "has_sig": False,
        "md5_digest": "4" * 32,
        "packagetype": "bdist_wheel",
        "python_version": "py3",
        "requires_python": ">=3.9",
        "size": 10,
        "upload_time": "2026-01-02T03:04:05",
        "upload_time_iso_8601": "2026-01-02T03:04:05.000000Z",
        "url": "https://unfetched.invalid/file",
        "yanked": False,
        "yanked_reason": None,
    }
    release = {
        "info": {"name": "fixture", "version": "1.0", "requires_python": ">=3.9", "yanked": False, "summary": "s"},
        "urls": [release_file, {**release_file, "filename": "fixture-1.0.tar.gz", "packagetype": "sdist"}],
        "vulnerabilities": [],
        "last_serial": 1,
    }
    projection = json.loads(_projection(_source("pypi_release", release, coordinate), coordinate).text)
    assert {"files[].digests", "files[].python_version", "files[].md5_digest"} <= set(projection["field_semantics"])
    assert projection["omitted_source_keys"] == ["info.summary", "last_serial", "files[].url"]
    fixed = canonical_bytes(
        {
            "field_semantics": dict(_FIELD_SEMANTICS),
            "source": "x" * 120,
            "fields_absent_in_source": ["info.requires_python", "info.yanked", "info.yanked_reason", "urls"],
        }
    )
    # The fixed representation overhead is small beside the unchanged no-clipping bound.
    assert len(fixed) < 4096 < _MAX_PROJECTION_CHARS == 32768


def test_long_omitted_key_list_stays_exact_without_clipping():
    from deepr.experts.preparation_service import _projection

    coordinate = _coordinate()
    info = {"name": "fixture", "version": "1.0", **{f"descriptive_key_{index:03}": "x" * 40 for index in range(40)}}
    result = _projection(_source("pypi_release", {"info": info, "urls": []}, coordinate), coordinate)
    projection = json.loads(result.text)
    assert projection["omitted_source_keys"] == [f"info.descriptive_key_{index:03}" for index in range(40)]
    assert result.omitted[0].startswith("40 source keys not projected (listed exactly in omitted_source_keys)")
    assert all(len(item) <= 512 for item in result.omitted)
