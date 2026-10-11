"""Strict, durable completed-chunk recovery for the shared study runner.

Records are candidate evidence, never execution authority. Callers attest and
pin the actual backend contract before preparing this store.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Any

from deepr.experts.study_lenses import LENSES
from deepr.utils.atomic_io import atomic_write_json

SCHEMA = "deepr-study-chunks-v1"
_MAX_BYTES = 2_000_000


class CheckpointWriteError(OSError):
    """Persistence is ambiguous; no subsequent model call may be attempted."""


class StudyExecutionStopped(RuntimeError):
    """A hard execution boundary stops the pass rather than failing each chunk."""


def identity(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value: str) -> Any:
    raise ValueError(f"nonfinite JSON value: {value}")


def read_record(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("checkpoint must be a regular file")
    with path.open("rb") as stream:
        raw = stream.read(_MAX_BYTES + 1)
    if len(raw) > _MAX_BYTES:
        raise ValueError("checkpoint exceeds byte limit")
    value = decode_json(raw)
    if not isinstance(value, dict):
        raise ValueError("checkpoint must be an object")
    return value


def decode_json(raw: str | bytes) -> Any:
    try:
        return json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except RecursionError as error:
        raise ValueError("JSON nesting exceeds decoder limits") from error


def response_items(response: dict[str, Any], output_field: str) -> list[dict[str, Any]]:
    """Validate form only, keeping the established array-alias compatibility."""
    if "error" in response or "errors" in response:
        raise ValueError("model returned an error envelope")
    aliases = {"results", "findings", "items", "failure_modes", "failures"}
    aliases.update(lens.output_field for lens in LENSES.values())
    if output_field in response:
        items = response[output_field]
    else:
        items = next((value for key, value in response.items() if key in aliases and isinstance(value, list)), None)
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ValueError("lens output must be an array of objects (an empty array is valid)")
    return items


def material_identity(material: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "source_sha256": entry.sha256,
            "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "chars": len(text),
            "origin": entry.origin_key,
            "title": entry.title,
            "publisher": entry.publisher,
        }
        for entry, text in material
    ]


class StudyCheckpoint:
    """One immutable candidate's successful chunks and measured durations."""

    def __init__(self, directory: Path, *, previous: Path | None = None, model_contract: dict[str, Any] | None = None):
        self.directory = directory
        self.previous = previous
        self.model_contract = model_contract or {}
        self.records: dict[str, dict[str, Any]] = {}
        self.notes: list[str] = []
        if os.name == "nt":
            self.notes.append(
                "Windows checkpoints use file fsync and atomic replacement; power-loss directory durability is not claimed."
            )
        self.manifest: dict[str, Any] = {}
        self.reused = 0

    def prepare(self, contract: dict[str, Any], prompts: dict[str, str]) -> str:
        self.manifest = {
            "schema_version": SCHEMA,
            "contract": contract,
            "contract_id": identity(contract),
            "prompts": prompts,
        }
        if self.previous:
            self._load_previous()
        self._write(self.directory / "manifest.json", self.manifest)
        # Copy verified evidence before dispatch, so another interrupted retry
        # cannot lose chunks that belonged to a later lens in the prior run.
        for key, record in self.records.items():
            self._write(self.directory / f"{key}.json", record)
        self.reused = len(self.records)
        return str(self.manifest["contract_id"])

    def _load_previous(self) -> None:
        if self.previous is None:
            return
        try:
            if self.previous.is_symlink() or self.previous.parent.is_symlink():
                raise ValueError("checkpoint candidate directory must not be a symbolic link")
            digest = self.model_contract.get("digest")
            if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                raise ValueError("no attested model digest")
            previous = read_record(self.previous / "manifest.json")
            if identity(previous) != identity(self.manifest):
                raise ValueError("study contract changed")
        except (OSError, ValueError, TypeError):
            self.notes.append(
                "Earlier chunk checkpoints were unavailable or stale; their study contract could not be verified."
            )
            return
        for key in self.manifest["prompts"]:
            path = self.previous / f"{key}.json"
            if not path.exists():
                continue
            try:
                record = read_record(path)
                self._validate(key, record)
                self.records[key] = record
            except (OSError, ValueError, TypeError, KeyError):
                self.notes.append(f"Rejected malformed chunk checkpoint {key}; this chunk will be read again.")

    def _validate(self, key: str, record: dict[str, Any]) -> None:
        if set(record) != {
            "schema_version",
            "contract_id",
            "chunk_id",
            "prompt_sha256",
            "response",
            "response_sha256",
            "elapsed_seconds",
        }:
            raise ValueError("unexpected chunk fields")
        if (
            record["schema_version"] != SCHEMA
            or record["contract_id"] != self.manifest["contract_id"]
            or record["chunk_id"] != key
            or record["prompt_sha256"] != self.manifest["prompts"][key]
        ):
            raise ValueError("chunk identity changed")
        response = record["response"]
        duration = record["elapsed_seconds"]
        if not isinstance(response, dict) or record["response_sha256"] != identity(response):
            raise ValueError("response identity changed")
        lens = next(lens for lens in self.manifest["contract"]["lenses"] if key.rsplit("-", 1)[0] == lens["key"])
        response_items(response, lens["output_field"])
        if type(duration) not in (int, float) or not math.isfinite(duration) or not 0 <= duration <= 21_600:
            raise ValueError("invalid chunk timing")

    def _write(self, path: Path, payload: dict[str, Any]) -> None:
        try:
            if len(json.dumps(payload, allow_nan=False).encode()) > _MAX_BYTES:
                raise ValueError("checkpoint exceeds byte limit")
            atomic_write_json(path, payload, fsync=True, fsync_parent=True)
        except (OSError, ValueError, TypeError) as error:
            # An implementation/OS error after replacement is ambiguous to the
            # caller. Remove that candidate so a retry cannot count it as done.
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            raise CheckpointWriteError(
                "Completed chunk could not be durably checkpointed; execution stopped."
            ) from error

    def lookup(self, key: str) -> dict[str, Any] | None:
        record = self.records.get(key)
        return record["response"] if record else None

    def complete(self, key: str, parsed: dict[str, Any], duration: float) -> None:
        record = {
            "schema_version": SCHEMA,
            "contract_id": self.manifest["contract_id"],
            "chunk_id": key,
            "prompt_sha256": self.manifest["prompts"][key],
            "response": parsed,
            "response_sha256": identity(parsed),
            "elapsed_seconds": round(duration, 6),
        }
        self._validate(key, record)
        self._write(self.directory / f"{key}.json", record)
        self.records[key] = record

    def progress(self) -> dict[str, Any]:
        durations = [float(record["elapsed_seconds"]) for record in self.records.values()]
        remaining = len(self.manifest.get("prompts", {})) - len(self.records)
        return {
            "chunks_total": len(self.manifest.get("prompts", {})),
            "chunks_completed": len(self.records),
            "chunks_reused": self.reused,
            "chunks_remaining": remaining,
            "timing_samples": len(durations),
            "estimated_study_seconds": round(sum(durations) / len(durations) * remaining, 1) if durations else None,
            "estimate_source": "measured_completed_chunks" if durations else "unknown",
        }
