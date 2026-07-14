"""Recovering the Antigravity headless answer from its transcript file."""

from __future__ import annotations

import json
import time

import pytest

from deepr.backends.plan_quota import antigravity_transcript
from deepr.backends.plan_quota.antigravity_transcript import (
    TranscriptOutputLimitError,
    TranscriptSnapshotError,
    TranscriptSnapshotTimeoutError,
    last_planner_response,
    recover_answer,
    transcript_snapshot,
)


def _write_transcript(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")


def _transcript_path(brain, conv_id):
    return brain / conv_id / ".system_generated" / "logs" / "transcript.jsonl"


def test_returns_last_planner_response(tmp_path):
    path = _transcript_path(tmp_path, "conv-1")
    _write_transcript(
        path,
        [
            {"type": "USER_INPUT", "content": "Reply with exactly: OK"},
            {"type": "PLANNER_RESPONSE", "content": "first draft"},
            {"type": "CONVERSATION_HISTORY"},
            {"type": "PLANNER_RESPONSE", "content": "OK"},
        ],
    )
    assert last_planner_response(path) == "OK"


def test_none_when_no_planner_response(tmp_path):
    path = _transcript_path(tmp_path, "conv-1")
    _write_transcript(path, [{"type": "USER_INPUT", "content": "hi"}])
    assert last_planner_response(path) is None


@pytest.mark.parametrize("prompt", ["  leading whitespace", "\n\n[Deepr invocation id: abc123]"])
def test_prompt_correlation_preserves_exact_boundary_whitespace(tmp_path, prompt):
    path = _transcript_path(tmp_path, "conv-whitespace")
    _write_transcript(
        path,
        [
            {"type": "USER_INPUT", "content": prompt},
            {"type": "PLANNER_RESPONSE", "content": "owned answer"},
        ],
    )

    assert last_planner_response(path, expected_prompt=prompt) == "owned answer"
    assert last_planner_response(path, expected_prompt=prompt.strip()) is None


def test_tolerates_malformed_trailing_line(tmp_path):
    path = _transcript_path(tmp_path, "conv-1")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"type": "PLANNER_RESPONSE", "content": "good"}) + "\n{partial, not json",
        encoding="utf-8",
    )
    assert last_planner_response(path) == "good"


def test_structured_content_blocks(tmp_path):
    path = _transcript_path(tmp_path, "conv-1")
    _write_transcript(
        path,
        [{"type": "PLANNER_RESPONSE", "content": [{"text": "line one"}, {"text": "line two"}]}],
    )
    assert last_planner_response(path) == "line one\nline two"


def test_recover_answer_picks_changed_transcript_from_baseline(tmp_path):
    prompt = "current prompt"
    old = _transcript_path(tmp_path, "old")
    new = _transcript_path(tmp_path, "new")
    _write_transcript(old, [{"type": "PLANNER_RESPONSE", "content": "stale"}])
    baseline = transcript_snapshot(tmp_path)
    _write_transcript(
        new,
        [
            {"type": "USER_INPUT", "content": prompt},
            {"type": "PLANNER_RESPONSE", "content": "fresh"},
        ],
    )

    assert recover_answer(tmp_path, baseline=baseline, expected_prompt=prompt) == "fresh"


def test_recover_answer_none_when_rapid_prior_transcript_is_unchanged(tmp_path):
    old = _transcript_path(tmp_path, "old")
    _write_transcript(old, [{"type": "PLANNER_RESPONSE", "content": "stale"}])
    baseline = transcript_snapshot(tmp_path)

    assert recover_answer(tmp_path, baseline=baseline, expected_prompt="current prompt") is None


def test_recover_answer_none_when_brain_missing(tmp_path):
    assert recover_answer(tmp_path / "nonexistent", baseline={}, expected_prompt="current prompt") is None


def test_changed_existing_transcript_is_recoverable(tmp_path):
    prompt = "current prompt"
    path = _transcript_path(tmp_path, "current")
    _write_transcript(
        path,
        [
            {"type": "USER_INPUT", "content": "prior prompt"},
            {"type": "PLANNER_RESPONSE", "content": "prior"},
        ],
    )
    baseline = transcript_snapshot(tmp_path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            "\n"
            + json.dumps({"type": "USER_INPUT", "content": prompt})
            + "\n"
            + json.dumps({"type": "PLANNER_RESPONSE", "content": "current answer"})
        )

    assert recover_answer(tmp_path, baseline=baseline, expected_prompt=prompt) == "current answer"


def test_recover_answer_rejects_old_match_after_unrelated_append(tmp_path):
    prompt = "Reply with exactly: OK"
    path = _transcript_path(tmp_path, "reused")
    _write_transcript(
        path,
        [
            {"type": "USER_INPUT", "content": prompt},
            {"type": "PLANNER_RESPONSE", "content": "old answer"},
        ],
    )
    baseline = transcript_snapshot(tmp_path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            "\n"
            + json.dumps({"type": "USER_INPUT", "content": "external prompt"})
            + "\n"
            + json.dumps({"type": "PLANNER_RESPONSE", "content": "external answer"})
        )

    assert recover_answer(tmp_path, baseline=baseline, expected_prompt=prompt) is None


def test_recover_answer_ignores_newer_unrelated_external_transcript(tmp_path):
    prompt = "current prompt"
    baseline = transcript_snapshot(tmp_path)
    owned = _transcript_path(tmp_path, "owned")
    unrelated = _transcript_path(tmp_path, "external")
    _write_transcript(
        owned,
        [
            {"type": "USER_INPUT", "content": prompt},
            {"type": "PLANNER_RESPONSE", "content": "owned answer"},
        ],
    )
    _write_transcript(
        unrelated,
        [
            {"type": "USER_INPUT", "content": "external prompt"},
            {"type": "PLANNER_RESPONSE", "content": "external answer"},
        ],
    )

    assert recover_answer(tmp_path, baseline=baseline, expected_prompt=prompt) == "owned answer"


def test_transcript_read_is_bounded_before_json_decode(tmp_path, monkeypatch):
    path = _transcript_path(tmp_path, "oversized")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * 65)
    monkeypatch.setattr(antigravity_transcript, "MAX_CAPTURE_BYTES", 64)

    with pytest.raises(TranscriptOutputLimitError, match="transcript exceeded"):
        last_planner_response(path)


def test_snapshot_rejects_history_beyond_bounded_file_count(tmp_path, monkeypatch):
    monkeypatch.setattr(antigravity_transcript, "_MAX_TRANSCRIPTS", 2)
    for index in range(3):
        _write_transcript(
            _transcript_path(tmp_path, f"conv-{index}"),
            [{"type": "USER_INPUT", "content": str(index)}],
        )

    with pytest.raises(TranscriptSnapshotError, match="history exceeds"):
        transcript_snapshot(tmp_path)


def test_snapshot_bounds_nonmatching_root_entries(tmp_path, monkeypatch):
    monkeypatch.setattr(antigravity_transcript, "_MAX_TRANSCRIPTS", 2)
    for index in range(3):
        (tmp_path / f"unrelated-{index}").mkdir()

    with pytest.raises(TranscriptSnapshotError, match="history exceeds"):
        transcript_snapshot(tmp_path)


def test_snapshot_honors_monotonic_deadline(tmp_path):
    _write_transcript(
        _transcript_path(tmp_path, "conv"),
        [{"type": "USER_INPUT", "content": "prompt"}],
    )

    with pytest.raises(TranscriptSnapshotTimeoutError, match="dispatch deadline"):
        transcript_snapshot(tmp_path, deadline=time.monotonic() - 1)


def test_recovery_uses_actual_read_bytes_for_aggregate_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(antigravity_transcript, "MAX_CAPTURE_BYTES", 160)
    first = _transcript_path(tmp_path, "first")
    second = _transcript_path(tmp_path, "second")
    records = [
        {"type": "USER_INPUT", "content": "external prompt"},
        {"type": "PLANNER_RESPONSE", "content": "x" * 30},
    ]
    _write_transcript(first, records)
    _write_transcript(second, records)

    def understated_stamp(path):
        order = 2 if path == first else 1
        return order, 1

    monkeypatch.setattr(antigravity_transcript, "_required_stamp", understated_stamp)

    with pytest.raises(TranscriptOutputLimitError, match="transcript exceeded"):
        recover_answer(tmp_path, baseline={}, expected_prompt="owned prompt")


def test_recovery_rejects_too_many_changed_transcripts(tmp_path, monkeypatch):
    monkeypatch.setattr(antigravity_transcript, "_MAX_CHANGED_TRANSCRIPTS", 1)
    for index in range(2):
        _write_transcript(
            _transcript_path(tmp_path, f"changed-{index}"),
            [{"type": "USER_INPUT", "content": str(index)}],
        )

    with pytest.raises(TranscriptOutputLimitError, match="changed transcripts"):
        recover_answer(tmp_path, baseline={}, expected_prompt="owned prompt")


def test_record_iteration_does_not_materialize_many_short_lines():
    class SplitForbidden(bytes):
        def splitlines(self, *args, **kwargs):
            raise AssertionError("bounded transcript iteration must remain lazy")

    payload = SplitForbidden(
        b"\n" * 100_000 + json.dumps({"type": "PLANNER_RESPONSE", "content": "answer"}).encode("utf-8")
    )

    records = list(antigravity_transcript._iter_transcript_records(payload))

    assert records[-1][1]["content"] == "answer"
