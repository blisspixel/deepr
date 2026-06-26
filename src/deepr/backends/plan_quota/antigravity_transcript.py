"""Recover the Antigravity (`agy`) headless answer from its transcript file.

`agy -p` (v1.0.12) drops its final answer from stdout under a non-TTY pipe: the
process exits 0 with empty stdout, so a subprocess caller cannot read the reply
(see plan-quota-cli-backends.md). The answer is still persisted to the CLI's own
per-conversation transcript:

    ~/.gemini/antigravity-cli/brain/<conv-id>/.system_generated/logs/transcript.jsonl

Each line is one JSON record ``{step_index, source, type, status, created_at,
content}``. The model's reply is the last record whose ``type`` is
``PLANNER_RESPONSE``; ``content`` is the answer text. This module finds the
transcript written by the run that just finished (newest file touched at or after
a recorded start time) and extracts that answer. It is deterministic form
extraction, never a judgement on the answer (AGENTIC_BALANCE).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_PLANNER_RESPONSE = "PLANNER_RESPONSE"
_TRANSCRIPT_GLOB = "*/.system_generated/logs/transcript.jsonl"


def antigravity_brain_dir() -> Path:
    """The Antigravity CLI per-conversation transcript root for this user."""
    return Path.home() / ".gemini" / "antigravity-cli" / "brain"


def _record_text(content: object) -> str:
    """Extract plain text from a transcript record's ``content`` field.

    Normally a string. Defensively handle a list of ``{"text": ...}`` blocks in
    case a future build returns structured content, so a format shift degrades to
    "no answer" rather than crashing.
    """
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [str(block.get("text", "")) for block in content if isinstance(block, dict)]
        return "\n".join(p for p in parts if p).strip()
    return ""


def last_planner_response(transcript_path: Path) -> str | None:
    """Return the last PLANNER_RESPONSE answer in one transcript, or None."""
    answer: str | None = None
    try:
        with transcript_path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue  # tolerate a partially written trailing line
                if isinstance(record, dict) and record.get("type") == _PLANNER_RESPONSE:
                    text = _record_text(record.get("content"))
                    if text:
                        answer = text
    except OSError as exc:
        logger.debug("could not read antigravity transcript %s: %s", transcript_path, exc)
        return None
    return answer


def recover_answer(brain_dir: Path, *, since: float) -> str | None:
    """Recover the headless answer from the transcript written since ``since``.

    ``since`` is an epoch seconds mark taken just before the CLI launched, so an
    older conversation's transcript is never mistaken for this run's. The newest
    transcript modified at or after that mark wins.
    """
    candidates = [
        path
        for path in brain_dir.glob(_TRANSCRIPT_GLOB)
        if _safe_mtime(path) >= since - 1.0  # 1s slack for filesystem mtime granularity
    ]
    if not candidates:
        return None
    newest = max(candidates, key=_safe_mtime)
    return last_planner_response(newest)


def _safe_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0
