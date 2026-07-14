"""Recover the Antigravity (`agy`) headless answer from its transcript file.

`agy -p` (v1.0.12) drops its final answer from stdout under a non-TTY pipe: the
process exits 0 with empty stdout, so a subprocess caller cannot read the reply
(see plan-quota-cli-backends.md). The answer is still persisted to the CLI's own
per-conversation transcript:

    ~/.gemini/antigravity-cli/brain/<conv-id>/.system_generated/logs/transcript.jsonl

Each line is one JSON record ``{step_index, source, type, status, created_at,
content}``. The model's reply is the last record whose ``type`` is
``PLANNER_RESPONSE`` after the current invocation's exact ``USER_INPUT``. This
module considers only transcripts changed from a pre-dispatch snapshot and, for
an existing transcript, only prompts appended after its baseline byte offset.
It is deterministic form extraction, never a judgement on the answer
(AGENTIC_BALANCE).
"""

from __future__ import annotations

import json
import logging
import tempfile
import time
from collections.abc import Iterator, Mapping
from io import BytesIO
from pathlib import Path
from typing import Any

from filelock import FileLock

from deepr.backends.plan_quota.cli_runner import MAX_CAPTURE_BYTES

logger = logging.getLogger(__name__)

_PLANNER_RESPONSE = "PLANNER_RESPONSE"
_TRANSCRIPT_SUFFIX = Path(".system_generated/logs/transcript.jsonl")
_MAX_TRANSCRIPTS = 256
_MAX_CHANGED_TRANSCRIPTS = 64
TranscriptSnapshot = dict[str, tuple[int, int]]


class TranscriptOutputLimitError(RuntimeError):
    """A transcript or recovered answer exceeded the shared capture ceiling."""


class TranscriptSnapshotError(RuntimeError):
    """Pre-dispatch transcript identity could not be captured safely."""


class TranscriptSnapshotTimeoutError(TranscriptSnapshotError):
    """The transcript baseline could not be captured within the dispatch budget."""


class _TranscriptEnumerationLimitError(RuntimeError):
    """The transcript root contained more entries than a bounded scan permits."""


class _TranscriptEnumerationTimeoutError(RuntimeError):
    """The bounded transcript-root scan exhausted its monotonic deadline."""


def antigravity_brain_dir() -> Path:
    """The Antigravity CLI per-conversation transcript root for this user."""
    return Path.home() / ".gemini" / "antigravity-cli" / "brain"


def _record_text(content: object, *, strip: bool = True) -> str:
    """Extract plain text from a transcript record's ``content`` field.

    Normally a string. Defensively handle a list of ``{"text": ...}`` blocks in
    case a future build returns structured content, so a format shift degrades to
    "no answer" rather than crashing.
    """
    if isinstance(content, str):
        return content.strip() if strip else content
    if isinstance(content, list):
        parts = [str(block.get("text", "")) for block in content if isinstance(block, dict)]
        text = "\n".join(p for p in parts if p)
        return text.strip() if strip else text
    return ""


def last_planner_response(
    transcript_path: Path,
    *,
    expected_prompt: str | None = None,
    minimum_prompt_offset: int = 0,
    max_bytes: int | None = None,
) -> str | None:
    """Return the last response correlated to an optional exact user input."""
    byte_limit = MAX_CAPTURE_BYTES if max_bytes is None else max_bytes
    return _planner_response_and_size(
        transcript_path,
        expected_prompt=expected_prompt,
        minimum_prompt_offset=minimum_prompt_offset,
        byte_limit=byte_limit,
    )[0]


def _planner_response_and_size(
    transcript_path: Path,
    *,
    expected_prompt: str | None,
    minimum_prompt_offset: int,
    byte_limit: int,
) -> tuple[str | None, int]:
    payload = _read_transcript_payload(transcript_path, byte_limit=byte_limit)
    if payload is None:
        return None, 0
    answer: str | None = None
    matched_prompt = expected_prompt is None
    for line_offset, record in _iter_transcript_records(payload):
        record_type = record.get("type")
        if record_type == "USER_INPUT" and expected_prompt is not None:
            answer = None
            matched_prompt = (
                line_offset >= minimum_prompt_offset
                and _record_text(record.get("content"), strip=False) == expected_prompt
            )
        elif record_type == _PLANNER_RESPONSE and matched_prompt:
            answer = _bounded_response_text(record)
    return answer, len(payload)


def _read_transcript_payload(transcript_path: Path, *, byte_limit: int) -> bytes | None:
    try:
        with transcript_path.open("rb") as handle:
            payload = handle.read(byte_limit + 1)
    except OSError as error:
        logger.debug("could not read antigravity transcript %s: %s", transcript_path, error)
        return None
    if len(payload) > byte_limit:
        raise TranscriptOutputLimitError("Antigravity transcript exceeded the capture limit")
    return payload


def _iter_transcript_records(payload: bytes) -> Iterator[tuple[int, dict[str, Any]]]:
    line_offset = 0
    for raw_line in BytesIO(payload):
        current_offset = line_offset
        line_offset += len(raw_line)
        line = raw_line.decode("utf-8").strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            yield current_offset, record


def _bounded_response_text(record: Mapping[str, object]) -> str | None:
    text = _record_text(record.get("content"))
    if not text:
        return None
    if len(text.encode("utf-8")) > MAX_CAPTURE_BYTES:
        raise TranscriptOutputLimitError("Antigravity answer exceeded the capture limit")
    return text


def transcript_snapshot(brain_dir: Path, *, deadline: float | None = None) -> TranscriptSnapshot:
    """Capture bounded identity metadata before an exclusively owned dispatch."""
    snapshot: TranscriptSnapshot = {}
    try:
        for path in _bounded_transcript_paths(brain_dir, deadline=deadline):
            snapshot[str(path)] = _required_stamp(path)
    except _TranscriptEnumerationLimitError as error:
        raise TranscriptSnapshotError("Antigravity transcript history exceeds the snapshot limit") from error
    except _TranscriptEnumerationTimeoutError as error:
        raise TranscriptSnapshotTimeoutError(
            "Antigravity transcript snapshot exceeded the dispatch deadline"
        ) from error
    except OSError as error:
        raise TranscriptSnapshotError("Antigravity transcript metadata is unavailable") from error
    return snapshot


def transcript_recovery_lock() -> FileLock:
    """Return the cross-process lock that serializes dispatch and recovery."""
    lock_dir = Path(tempfile.gettempdir()) / "deepr-plan-quota"
    lock_dir.mkdir(parents=True, exist_ok=True)
    return FileLock(str(lock_dir / "antigravity-transcript.lock"), thread_local=False)


def recover_answer(
    brain_dir: Path,
    *,
    baseline: Mapping[str, tuple[int, int]],
    expected_prompt: str,
) -> str | None:
    """Recover the headless answer from the transcript changed by this run.

    Callers hold ``transcript_recovery_lock`` across the subprocess dispatch and
    this read. Only a new or changed transcript can qualify, so a rapid prior
    invocation cannot be promoted as the current answer.
    """
    candidates = _changed_transcripts(brain_dir, baseline=baseline)
    if not candidates:
        return None
    remaining_bytes = MAX_CAPTURE_BYTES
    for path, current_stamp in candidates:
        prior_stamp = baseline.get(str(path))
        prior_size = prior_stamp[1] if prior_stamp is not None and current_stamp[1] >= prior_stamp[1] else 0
        answer, bytes_read = _planner_response_and_size(
            path,
            expected_prompt=expected_prompt,
            minimum_prompt_offset=prior_size,
            byte_limit=remaining_bytes,
        )
        remaining_bytes -= bytes_read
        if answer is not None:
            return answer
    return None


def _changed_transcripts(
    brain_dir: Path,
    *,
    baseline: Mapping[str, tuple[int, int]],
) -> list[tuple[Path, tuple[int, int]]]:
    candidates: list[tuple[Path, tuple[int, int]]] = []
    try:
        for path in _bounded_transcript_paths(brain_dir):
            stamp = _required_stamp(path)
            if stamp == baseline.get(str(path)):
                continue
            if len(candidates) >= _MAX_CHANGED_TRANSCRIPTS:
                raise TranscriptOutputLimitError("Antigravity changed transcripts exceed the recovery limit")
            candidates.append((path, stamp))
    except _TranscriptEnumerationLimitError as error:
        raise TranscriptOutputLimitError("Antigravity transcript history exceeds the recovery limit") from error
    except OSError as error:
        raise RuntimeError("Antigravity transcript metadata is unavailable") from error
    candidates.sort(key=lambda item: item[1][0], reverse=True)
    return candidates


def _required_stamp(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_mtime_ns, stat.st_size


def _bounded_transcript_paths(
    brain_dir: Path,
    *,
    deadline: float | None = None,
) -> Iterator[Path]:
    """Yield transcript files while bounding all root-directory enumeration."""
    try:
        for index, entry in enumerate(brain_dir.iterdir()):
            if deadline is not None and time.monotonic() >= deadline:
                raise _TranscriptEnumerationTimeoutError
            if index >= _MAX_TRANSCRIPTS:
                raise _TranscriptEnumerationLimitError
            transcript = entry / _TRANSCRIPT_SUFFIX
            if transcript.is_file():
                yield transcript
    except FileNotFoundError:
        return
