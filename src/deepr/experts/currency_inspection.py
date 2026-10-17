"""Read-only inspection of whether an expert can say a claim is current.

The packet reports stored clocks and explicit gaps. It does not fetch, it
does not call a model, and it does not write canonical expert state. A file
date, a decayed confidence, and an empty end are not a currentness verdict.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from deepr.experts.beliefs import BeliefStore
from deepr.experts.expert_layout import part_in
from deepr.experts.position_ledger import LedgerUnreadableError, load_ledger
from deepr.experts.world_validity import project_world_validity

INSPECTION_SCHEMA = "deepr-currency-inspection-v1"
_HASH_RELATIVE = (
    "beliefs/beliefs.json",
    "beliefs/events.jsonl",
    "beliefs/mutation_audit.jsonl",
    "corpus/index.jsonl",
)


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_hashes(expert_dir: Path) -> dict[str, str | None]:
    hashes = {relative: _sha256(expert_dir / relative) for relative in _HASH_RELATIVE}
    history = part_in(expert_dir, "hold_history")
    try:
        key = history.relative_to(expert_dir).as_posix()
    except ValueError:
        key = str(history)
    hashes[key] = _sha256(history)
    return hashes


def _corpus_summary(expert_dir: Path) -> dict[str, Any]:
    path = expert_dir / "corpus" / "index.jsonl"
    if not path.is_file():
        return {
            "present": False,
            "active_sources": 0,
            "fetched_at_min": None,
            "fetched_at_max": None,
            "unreadable_lines": 0,
            "dates_are_fetch_times": True,
            "currentness_certified": False,
        }
    active = 0
    fetched: list[str] = []
    unreadable = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError:
                unreadable += 1
                continue
            if not isinstance(row, dict):
                unreadable += 1
                continue
            if not str(row.get("superseded_by") or "").strip():
                active += 1
            stamp = str(row.get("fetched_at") or "").strip()
            if stamp:
                fetched.append(stamp)
    fetched.sort()
    return {
        "present": True,
        "active_sources": active,
        "fetched_at_min": fetched[0] if fetched else None,
        "fetched_at_max": fetched[-1] if fetched else None,
        "unreadable_lines": unreadable,
        "dates_are_fetch_times": True,
        "currentness_certified": False,
    }


def _position_summary(expert_dir: Path, expert_name: str) -> dict[str, Any]:
    path = part_in(expert_dir, "hold_history")
    if not path.is_file():
        return {"present": False, "clock": "record_time", "world_time_recorded": False}
    try:
        ledger = load_ledger(path, expert_name=expert_name)
    except LedgerUnreadableError as exc:
        return {
            "present": True,
            "unreadable": True,
            "error": str(exc),
            "clock": "record_time",
            "world_time_recorded": False,
        }
    return {
        "present": True,
        "unreadable": False,
        "versions": len(ledger.versions),
        "live": len(ledger.live),
        "clock": "record_time",
        "world_time_recorded": False,
    }


def inspect_currency(
    expert_dir: Path,
    expert_name: str,
    *,
    question: str | None = None,
) -> dict[str, Any]:
    """Build the inspection packet from one expert directory."""
    before = _file_hashes(expert_dir)
    belief_dir = expert_dir / "beliefs"
    store = BeliefStore(expert_name, storage_dir=belief_dir, read_only=True)
    readable = not bool(getattr(store, "_unreadable", False))
    world = project_world_validity(store) if readable else None
    question_text = question.strip() if question else ""
    packet: dict[str, Any] = {
        "schema": INSPECTION_SCHEMA,
        "expert": expert_name,
        "question_sha256": hashlib.sha256(question_text.encode("utf-8")).hexdigest() if question_text else None,
        "live_check": "not_examined",
        "further_research": "not_judged",
        "canonical_mutation": False,
        "belief_store_readable": readable,
        "world_validity": world,
        "corpus": _corpus_summary(expert_dir),
        "positions": _position_summary(expert_dir, expert_name),
        "file_sha256": before,
    }
    packet["file_sha256_after"] = _file_hashes(expert_dir)
    packet["files_unchanged"] = packet["file_sha256"] == packet["file_sha256_after"]
    return packet
