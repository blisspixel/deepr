"""Actual chunk boundaries survive interruption without repeating accepted work."""

import asyncio
import json
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from deepr.experts import study_checkpoint
from deepr.experts.study import run_study
from deepr.experts.study_checkpoint import CheckpointWriteError, StudyCheckpoint
from deepr.experts.study_lenses import LENSES

from .test_study import corpus  # noqa: F401

CONTRACT = {"model": "fixture", "digest": "a" * 64, "options": {"num_ctx": 16384, "num_predict": 16000}}


@pytest.mark.parametrize(
    "response", ['[{"fail_patterns": []}]', '[{"fail_patterns": []},', '```json\n[{"fail_patterns": []}]\n```']
)
@pytest.mark.asyncio
async def test_outer_array_is_not_salvaged_as_completed_object(corpus, tmp_path, response):
    chunks = checkpoint(tmp_path, "first")
    result = await run(corpus, chunks, AsyncMock(return_value=response))
    assert result.outcomes[0].status == "parse_failed"
    assert chunks.records == {}
    retry = AsyncMock(return_value='{"fail_patterns": []}')
    resumed = checkpoint(tmp_path, "second", "first")
    await run(corpus, resumed, retry)
    assert resumed.reused == 0
    assert retry.await_count == len(corpus.iter_study_chunks(chunk_chars=70))


def checkpoint(tmp_path, name, previous=None, contract=None):
    return StudyCheckpoint(
        tmp_path / name, previous=tmp_path / previous if previous else None, model_contract=contract or CONTRACT
    )


async def run(corpus, chunks, completion, **kwargs):
    return await run_study(
        expert_name="E",
        corpus=corpus,
        completion=completion,
        lens_keys=["failure"],
        chunk_chars=70,
        model="fixture",
        capacity_source="local:fixture",
        chunk_checkpoint=chunks,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_cancel_after_two_completed_chunks_retry_does_not_repeat_them(corpus, tmp_path):
    first = checkpoint(tmp_path, "first")
    completion = AsyncMock(side_effect=['{"fail_patterns": []}', '{"fail_patterns": []}', asyncio.CancelledError()])
    with pytest.raises(asyncio.CancelledError):
        await run(corpus, first, completion)
    assert len(first.records) == 2
    assert len(list(first.directory.glob("failure-*.json"))) == 2
    retry = AsyncMock(return_value='{"fail_patterns": []}')
    second = checkpoint(tmp_path, "second", "first")
    result = await run(corpus, second, retry)
    assert result.outcomes[0].status == "ok"
    assert second.reused == 2
    assert retry.await_count == len(corpus.iter_study_chunks(chunk_chars=70)) - 2
    assert len(first.records) == 2, "earlier operation evidence stays unchanged"


@pytest.mark.asyncio
async def test_empty_valid_chunks_are_reusable_and_copied_before_dispatch(corpus, tmp_path):
    first = checkpoint(tmp_path, "first")
    await run(corpus, first, AsyncMock(return_value='{"fail_patterns": []}'))
    second = checkpoint(tmp_path, "second", "first")
    forbidden = AsyncMock(side_effect=AssertionError("No new inference for complete chunks"))
    result = await run(corpus, second, forbidden)
    forbidden.assert_not_awaited()
    assert result.outcomes[0].status == "ok"
    assert len(second.records) == len(first.records)
    for key in first.records:
        assert (first.directory / f"{key}.json").read_bytes() == (second.directory / f"{key}.json").read_bytes()


@pytest.mark.asyncio
async def test_failed_parse_is_not_checkpointed_or_reused(corpus, tmp_path):
    first = checkpoint(tmp_path, "first")
    completion = AsyncMock(side_effect=["not JSON"] + ['{"fail_patterns": []}'] * 20)
    result = await run(corpus, first, completion)
    assert result.outcomes[0].status == "partial"
    retry = AsyncMock(return_value='{"fail_patterns": []}')
    second = checkpoint(tmp_path, "second", "first")
    await run(corpus, second, retry)
    assert retry.await_count == 1
    assert second.reused == len(first.records)


@pytest.mark.asyncio
async def test_checkpoint_write_failure_stops_before_next_dispatch(corpus, tmp_path, monkeypatch):
    real_write = study_checkpoint.atomic_write_json
    writes = []

    def write(path, payload, **kwargs):
        writes.append((path.name, kwargs))
        if path.name == "failure-0001.json":
            raise OSError("simulated disk failure")
        return real_write(path, payload, **kwargs)

    monkeypatch.setattr(study_checkpoint, "atomic_write_json", write)
    completion = AsyncMock(return_value='{"fail_patterns": []}')
    chunks = checkpoint(tmp_path, "first")
    with pytest.raises(CheckpointWriteError, match="durably checkpointed"):
        await run(corpus, chunks, completion)
    assert completion.await_count == 1
    assert chunks.records == {}
    assert all(options["fsync"] is True for _, options in writes)
    assert all(options["fsync_parent"] is True for _, options in writes)


MALFORMED_RESPONSES = [
    {},
    {"error": "generation failed"},
    {"errors": [], "fail_patterns": []},
    {"fail_patterns": "unavailable"},
    {"fail_patterns": None, "results": []},
    {"fail_patterns": ["not an object"]},
    {"fail_patterns": [{"name": "One"}, 2]},
    {"unrecognized": []},
]


@pytest.mark.parametrize("response", MALFORMED_RESPONSES)
@pytest.mark.asyncio
async def test_malformed_model_shape_is_not_completed_or_reused(corpus, tmp_path, response):
    first = checkpoint(tmp_path, "first")
    result = await run(corpus, first, AsyncMock(return_value=json.dumps(response)))
    assert result.outcomes[0].status == "parse_failed"
    assert first.records == {}
    completion = AsyncMock(return_value='{"fail_patterns": []}')
    second = checkpoint(tmp_path, "second", "first")
    await run(corpus, second, completion)
    assert second.reused == 0
    assert completion.await_count == len(corpus.iter_study_chunks(chunk_chars=70))


@pytest.mark.parametrize("response", MALFORMED_RESPONSES)
@pytest.mark.asyncio
async def test_structurally_invalid_old_record_is_rejected_even_with_matching_hash(corpus, tmp_path, response):
    first = checkpoint(tmp_path, "first")
    await run(corpus, first, AsyncMock(return_value='{"fail_patterns": []}'))
    path = first.directory / "failure-0001.json"
    record = json.loads(path.read_text())
    record.update(response=response, response_sha256=study_checkpoint.identity(response))
    path.write_text(json.dumps(record))
    completion = AsyncMock(return_value='{"fail_patterns": []}')
    second = checkpoint(tmp_path, "second", "first")
    await run(corpus, second, completion)
    assert completion.await_count == 1
    assert second.reused == len(first.records) - 1
    assert any("Rejected malformed" in note for note in second.notes)


@pytest.mark.parametrize("field", ["fail_patterns", "failure_modes", "failures", "results", "findings", "items"])
@pytest.mark.asyncio
async def test_recognized_empty_array_contracts_remain_completed(corpus, tmp_path, field):
    first = checkpoint(tmp_path, "first")
    result = await run(corpus, first, AsyncMock(return_value=json.dumps({field: []})))
    assert result.outcomes[0].status == "ok"
    second = checkpoint(tmp_path, "second", "first")
    completion = AsyncMock(side_effect=AssertionError("Completed empty arrays must be reused"))
    await run(corpus, second, completion)
    completion.assert_not_awaited()


@pytest.mark.parametrize(
    "response",
    [
        '{"fail_patterns": [], "fail_patterns": []}',
        '{"fail_patterns": [{"name": "A", "name": "B"}]}',
        '{"fail_patterns": [',
    ],
)
@pytest.mark.asyncio
async def test_duplicate_model_json_keys_and_truncated_responses_are_not_completed(corpus, tmp_path, response):
    chunks = checkpoint(tmp_path, "first")
    result = await run(corpus, chunks, AsyncMock(return_value=response))
    assert result.outcomes[0].status == "parse_failed"
    assert chunks.records == {}


@pytest.mark.asyncio
async def test_directory_sync_failure_stops_next_dispatch_and_does_not_reuse_record(corpus, tmp_path, monkeypatch):
    from deepr.utils import atomic_io

    real_sync = atomic_io._fsync_parent_chain
    calls = 0

    def sync(directory):
        nonlocal calls
        calls += 1
        if calls == 2:  # Manifest succeeded; first completed record cannot be acknowledged.
            raise OSError("directory sync failed")
        real_sync(directory)

    monkeypatch.setattr(atomic_io, "_fsync_parent_chain", sync)
    first = checkpoint(tmp_path, "first")
    completion = AsyncMock(return_value='{"fail_patterns": []}')
    with pytest.raises(CheckpointWriteError):
        await run(corpus, first, completion)
    assert completion.await_count == 1
    assert first.records == {}
    assert not (first.directory / "failure-0001.json").exists()
    monkeypatch.setattr(atomic_io, "_fsync_parent_chain", real_sync)
    second = checkpoint(tmp_path, "second", "first")
    retry = AsyncMock(return_value='{"fail_patterns": []}')
    await run(corpus, second, retry)
    assert second.reused == 0
    assert retry.await_count == len(corpus.iter_study_chunks(chunk_chars=70))


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", "future"),
        ("contract_id", "b" * 64),
        ("chunk_id", "../other"),
        ("prompt_sha256", "c" * 64),
        ("response_sha256", "d" * 64),
        ("response", []),
        ("elapsed_seconds", True),
        ("elapsed_seconds", -1),
        ("elapsed_seconds", float("nan")),
        ("unexpected", "field"),
    ],
)
@pytest.mark.asyncio
async def test_corrupt_record_is_rejected_and_only_that_chunk_is_re_read(corpus, tmp_path, field, value):
    first = checkpoint(tmp_path, "first")
    await run(corpus, first, AsyncMock(return_value='{"fail_patterns": []}'))
    path = first.directory / "failure-0001.json"
    payload = json.loads(path.read_text())
    payload[field] = value
    path.write_text(json.dumps(payload))
    second = checkpoint(tmp_path, "second", "first")
    completion = AsyncMock(return_value='{"fail_patterns": []}')
    await run(corpus, second, completion)
    assert completion.await_count == 1
    assert any("Rejected malformed" in note for note in second.notes)


@pytest.mark.asyncio
async def test_duplicate_json_keys_are_rejected(corpus, tmp_path):
    first = checkpoint(tmp_path, "first")
    await run(corpus, first, AsyncMock(return_value='{"fail_patterns": []}'))
    path = first.directory / "failure-0001.json"
    path.write_text(path.read_text().replace('"elapsed_seconds":', '"elapsed_seconds": 3, "elapsed_seconds":'))
    completion = AsyncMock(return_value='{"fail_patterns": []}')
    await run(corpus, checkpoint(tmp_path, "second", "first"), completion)
    assert completion.await_count == 1


def test_checkpoint_reader_refuses_nonregular_candidates(tmp_path):
    with pytest.raises(ValueError, match="regular file"):
        study_checkpoint.read_record(tmp_path)


@pytest.mark.asyncio
async def test_ambiguous_write_is_removed_and_retried(corpus, tmp_path, monkeypatch):
    real_write = study_checkpoint.atomic_write_json

    def ambiguous(path, payload, **options):
        real_write(path, payload, **options)
        if path.name == "failure-0001.json":
            raise OSError("write outcome ambiguous")

    first = checkpoint(tmp_path, "first")
    monkeypatch.setattr(study_checkpoint, "atomic_write_json", ambiguous)
    with pytest.raises(CheckpointWriteError):
        await run(corpus, first, AsyncMock(return_value='{"fail_patterns": []}'))
    assert not (first.directory / "failure-0001.json").exists()
    monkeypatch.setattr(study_checkpoint, "atomic_write_json", real_write)
    second = checkpoint(tmp_path, "second", "first")
    completion = AsyncMock(return_value='{"fail_patterns": []}')
    await run(corpus, second, completion)
    assert second.reused == 0
    assert completion.await_count == len(corpus.iter_study_chunks(chunk_chars=70))


@pytest.mark.parametrize("change", ["corpus_limit", "chunk_size", "model", "digest", "options", "lens", "material"])
@pytest.mark.asyncio
async def test_changed_effective_contract_cannot_reuse_chunks(corpus, tmp_path, monkeypatch, change):
    first = checkpoint(tmp_path, "first")
    await run(corpus, first, AsyncMock(return_value='{"fail_patterns": []}'))
    contract = dict(CONTRACT)
    arguments = {}
    if change == "corpus_limit":
        arguments["max_corpus_chars"] = 200
    if change == "digest":
        contract["digest"] = "b" * 64
    if change == "options":
        contract["options"] = {"num_ctx": 4096, "num_predict": 16000}
    if change == "model":
        contract["model"] = "other"
    if change == "lens":
        monkeypatch.setitem(LENSES, "failure", replace(LENSES["failure"], prompt="Changed lens"))
    if change == "material":
        corpus.add("New retained source", origin_key="url:another.example")
    second = checkpoint(tmp_path, "second", "first", contract)
    completion = AsyncMock(return_value='{"fail_patterns": []}')
    if change == "chunk_size":
        await run_study(
            expert_name="E",
            corpus=corpus,
            completion=completion,
            lens_keys=["failure"],
            chunk_chars=80,
            model="fixture",
            capacity_source="local:fixture",
            chunk_checkpoint=second,
        )
    else:
        await run(corpus, second, completion, **arguments)
    assert second.reused == 0
    assert completion.await_count > 0
    assert any("stale" in note for note in second.notes)


@pytest.mark.asyncio
async def test_eta_starts_unknown_then_uses_a_real_completed_chunk_without_probe(corpus, tmp_path):
    progress = []
    completion = AsyncMock(return_value='{"fail_patterns": []}')
    chunks = checkpoint(tmp_path, "first")
    await run(corpus, chunks, completion, on_chunk_progress=lambda value: progress.append(value))
    assert progress[0]["estimated_study_seconds"] is None
    assert progress[0]["timing_samples"] == 0
    assert progress[1]["timing_samples"] == 1
    assert progress[1]["estimated_study_seconds"] is not None
    assert completion.await_count == len(corpus.iter_study_chunks(chunk_chars=70))
