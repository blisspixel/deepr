"""Recovering the Antigravity headless answer from its transcript file."""

from __future__ import annotations

import json
import os

from deepr.backends.plan_quota.antigravity_transcript import (
    last_planner_response,
    recover_answer,
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


def test_recover_answer_picks_newest_since_mark(tmp_path):
    old = _transcript_path(tmp_path, "old")
    new = _transcript_path(tmp_path, "new")
    _write_transcript(old, [{"type": "PLANNER_RESPONSE", "content": "stale"}])
    _write_transcript(new, [{"type": "PLANNER_RESPONSE", "content": "fresh"}])
    # Make 'old' clearly older than the run start, 'new' clearly after it.
    base = 1_000_000.0
    os.utime(old, (base - 100, base - 100))
    os.utime(new, (base + 10, base + 10))

    assert recover_answer(tmp_path, since=base) == "fresh"


def test_recover_answer_none_when_nothing_new(tmp_path):
    old = _transcript_path(tmp_path, "old")
    _write_transcript(old, [{"type": "PLANNER_RESPONSE", "content": "stale"}])
    base = 1_000_000.0
    os.utime(old, (base - 100, base - 100))

    assert recover_answer(tmp_path, since=base) is None


def test_recover_answer_none_when_brain_missing(tmp_path):
    assert recover_answer(tmp_path / "nonexistent", since=0.0) is None
