"""Crash-safe local storage for durable expert investigations."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

from filelock import FileLock
from filelock import Timeout as FileLockTimeout

from deepr.config import load_config
from deepr.experts.investigation.models import (
    Phase,
    RunState,
    canonical_json,
    event_payload,
    initial_usage,
    sha256_bytes,
    utc_now,
    validate_plan,
)
from deepr.utils.atomic_io import append_jsonl_durable, atomic_write_bytes, atomic_write_json

_RUN_ID_RE = re.compile(r"^inv_[a-z0-9_]{4,80}$")
_ARTIFACT_COMPONENT_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,99}$")


class InvestigationStorageError(RuntimeError):
    """Raised when durable investigation state cannot be trusted."""


class InvestigationBusyError(InvestigationStorageError):
    """Raised when another process owns the run executor lock."""


class InvestigationNotFoundError(InvestigationStorageError):
    """Raised for an unknown run without leaking unrelated paths."""


def _safe_run_id(value: Any) -> str:
    normalized = str(value or "")
    if not _RUN_ID_RE.fullmatch(normalized):
        raise InvestigationStorageError("invalid investigation run id")
    return normalized


def _artifact_component(value: str, *, field_name: str) -> str:
    normalized = value.strip().lower()
    if not _ARTIFACT_COMPONENT_RE.fullmatch(normalized):
        raise InvestigationStorageError(f"invalid artifact {field_name}")
    return normalized


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InvestigationStorageError(f"could not read trusted {label}") from exc
    if not isinstance(payload, dict):
        raise InvestigationStorageError(f"trusted {label} is not an object")
    return payload


class InvestigationStore:
    """One configured-results-root repository for investigation runs."""

    def __init__(self, root: str | Path | None = None) -> None:
        configured = Path(load_config()["results_dir"]) / "investigations"
        self.root = Path(root) if root is not None else configured

    def run_dir(self, run_id: str) -> Path:
        return self.root / _safe_run_id(run_id)

    def _require_run_dir(self, run_id: str) -> Path:
        path = self.run_dir(run_id)
        if not path.is_dir():
            raise InvestigationNotFoundError("investigation not found")
        return path

    def create(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Create or idempotently reopen a run from an immutable plan."""
        validated = validate_plan(plan)
        run_id = _safe_run_id(validated["run_id"])
        path = self.run_dir(run_id)
        self.root.mkdir(parents=True, exist_ok=True)
        with FileLock(str(self.root / f".{run_id}.create.lock"), timeout=10):
            plan_path = path / "plan.json"
            if plan_path.exists():
                existing = self.load_plan(run_id)
                if existing["plan_sha256"] != validated["plan_sha256"]:
                    raise InvestigationStorageError("run id already belongs to a different plan")
                return self.load_state(run_id)
            path.mkdir(parents=False, exist_ok=False)
            atomic_write_json(plan_path, validated, sort_keys=True, fsync=True)
            state = {
                "schema_version": "deepr-investigation-state-v1",
                "kind": "deepr.expert.investigation_state",
                "run_id": run_id,
                "plan_sha256": validated["plan_sha256"],
                "version": 1,
                "state": RunState.PLANNED.value,
                "phase": Phase.PREFLIGHT.value,
                "usage": initial_usage(),
                "artifacts": {},
                "errors": [],
                "created_at": utc_now(),
                "updated_at": utc_now(),
            }
            atomic_write_json(path / "state.json", state, sort_keys=True, fsync=True)
            atomic_write_json(
                path / "control.json",
                {"requested": "run", "revision": 1, "updated_at": utc_now()},
                sort_keys=True,
                fsync=True,
            )
            self.append_event(
                run_id,
                event_type="run_created",
                phase=Phase.PREFLIGHT,
                status=RunState.PLANNED,
                detail={"plan_sha256": validated["plan_sha256"]},
            )
            return state

    def load_plan(self, run_id: str) -> dict[str, Any]:
        payload = _load_json(self._require_run_dir(run_id) / "plan.json", label="investigation plan")
        return validate_plan(payload)

    def load_state(self, run_id: str) -> dict[str, Any]:
        payload = _load_json(self._require_run_dir(run_id) / "state.json", label="investigation state")
        if payload.get("run_id") != run_id or payload.get("kind") != "deepr.expert.investigation_state":
            raise InvestigationStorageError("investigation state identity mismatch")
        return payload

    def save_state(self, run_id: str, state: dict[str, Any], *, expected_version: int | None = None) -> dict[str, Any]:
        path = self._require_run_dir(run_id) / "state.json"
        with FileLock(str(path.with_suffix(".json.lock")), timeout=10):
            current = _load_json(path, label="investigation state")
            version = int(current.get("version", 0))
            if expected_version is not None and version != expected_version:
                raise InvestigationStorageError("investigation state changed during update")
            updated = cast(dict[str, Any], json.loads(canonical_json(state)))
            if updated.get("run_id") != run_id or updated.get("plan_sha256") != current.get("plan_sha256"):
                raise InvestigationStorageError("investigation state identity cannot change")
            updated["version"] = version + 1
            updated["updated_at"] = utc_now()
            atomic_write_json(path, updated, sort_keys=True, fsync=True)
            return updated

    def load_control(self, run_id: str) -> dict[str, Any]:
        return _load_json(self._require_run_dir(run_id) / "control.json", label="investigation control")

    def request_control(self, run_id: str, action: str) -> dict[str, Any]:
        requested = action.strip().casefold()
        if requested not in {"run", "pause", "cancel"}:
            raise InvestigationStorageError("control action must be run, pause, or cancel")
        path = self._require_run_dir(run_id) / "control.json"
        with FileLock(str(path.with_suffix(".json.lock")), timeout=10):
            current = _load_json(path, label="investigation control")
            payload = {
                "requested": requested,
                "revision": int(current.get("revision", 0)) + 1,
                "updated_at": utc_now(),
            }
            atomic_write_json(path, payload, sort_keys=True, fsync=True)
            return payload

    @contextmanager
    def execution_lock(self, run_id: str, *, timeout_seconds: float = 0.0) -> Iterator[None]:
        path = self._require_run_dir(run_id) / "execute.lock"
        lock = FileLock(str(path))
        try:
            lock.acquire(timeout=max(0.0, timeout_seconds))
        except FileLockTimeout as exc:
            raise InvestigationBusyError("investigation already has an active executor") from exc
        try:
            yield
        finally:
            lock.release()

    def append_event(
        self,
        run_id: str,
        *,
        event_type: str,
        phase: Phase | str,
        status: RunState | str,
        detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        events_path = self._require_run_dir(run_id) / "events.jsonl"
        with FileLock(str(events_path.with_suffix(".jsonl.lock")), timeout=10):
            sequence = 1
            if events_path.exists():
                try:
                    lines = [line for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
                    if lines:
                        last = json.loads(lines[-1])
                        sequence = int(last["sequence"]) + 1
                except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                    raise InvestigationStorageError("event journal cannot be extended safely") from exc
            event = event_payload(
                run_id=run_id,
                sequence=sequence,
                event_type=event_type,
                phase=phase,
                status=status,
                detail=detail,
            )
            try:
                append_jsonl_durable(events_path, event, fsync=True)
            except OSError as exc:
                raise InvestigationStorageError("event journal append failed") from exc
            return event

    def load_events(self, run_id: str) -> list[dict[str, Any]]:
        path = self._require_run_dir(run_id) / "events.jsonl"
        if not path.exists():
            return []
        events: list[dict[str, Any]] = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    payload = json.loads(line)
                    if not isinstance(payload, dict):
                        raise ValueError("event must be an object")
                    events.append(payload)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise InvestigationStorageError("event journal is invalid") from exc
        return events

    def disk_usage(self, run_id: str) -> int:
        path = self._require_run_dir(run_id)
        total = 0
        try:
            for item in path.rglob("*"):
                if item.is_file() and not item.name.endswith(".lock"):
                    total += item.stat().st_size
        except OSError as exc:
            raise InvestigationStorageError("could not measure investigation disk usage") from exc
        return total

    def write_artifact(
        self,
        run_id: str,
        *,
        phase: Phase | str,
        key: str,
        payload: dict[str, Any],
        max_disk_bytes: int,
    ) -> dict[str, Any]:
        phase_name = _artifact_component(str(phase), field_name="phase")
        key_name = _artifact_component(key, field_name="key")
        run_dir = self._require_run_dir(run_id)
        path = run_dir / "artifacts" / phase_name / f"{key_name}.json"
        encoded = canonical_json(payload).encode("utf-8")
        digest = sha256_bytes(encoded)
        if path.exists():
            try:
                existing = path.read_bytes()
            except OSError as exc:
                raise InvestigationStorageError("could not verify existing artifact") from exc
            if sha256_bytes(existing) != digest:
                raise InvestigationStorageError("artifact idempotency conflict")
        else:
            if self.disk_usage(run_id) + len(encoded) > max_disk_bytes:
                raise InvestigationStorageError("investigation disk ceiling would be exceeded")
            try:
                atomic_write_bytes(path, encoded, fsync=True)
            except OSError as exc:
                raise InvestigationStorageError("artifact write failed") from exc
        return {
            "path": path.relative_to(run_dir).as_posix(),
            "sha256": digest,
            "bytes": path.stat().st_size,
            "phase": phase_name,
            "key": key_name,
        }

    def write_source_snapshot(
        self,
        run_id: str,
        *,
        content: str,
        content_sha256: str,
        max_disk_bytes: int,
    ) -> dict[str, Any]:
        """Persist one verified content-addressed raw retrieval snapshot."""
        encoded = content.encode("utf-8")
        if sha256_bytes(encoded) != content_sha256:
            raise InvestigationStorageError("source snapshot content hash mismatch")
        run_dir = self._require_run_dir(run_id)
        path = run_dir / "artifacts" / "sources" / f"{content_sha256}.txt"
        if not path.exists():
            if self.disk_usage(run_id) + len(encoded) > max_disk_bytes:
                raise InvestigationStorageError("investigation disk ceiling would be exceeded")
            try:
                atomic_write_bytes(path, encoded, fsync=True)
            except OSError as exc:
                raise InvestigationStorageError("source snapshot write failed") from exc
        elif sha256_bytes(path.read_bytes()) != content_sha256:
            raise InvestigationStorageError("existing source snapshot failed hash verification")
        return {
            "path": path.relative_to(run_dir).as_posix(),
            "sha256": content_sha256,
            "bytes": path.stat().st_size,
            "phase": "sources",
            "key": content_sha256,
        }

    def read_artifact(self, run_id: str, reference: dict[str, Any]) -> dict[str, Any]:
        run_dir = self._require_run_dir(run_id)
        relative = Path(str(reference.get("path", "")))
        path = (run_dir / relative).resolve()
        try:
            path.relative_to(run_dir.resolve())
        except ValueError as exc:
            raise InvestigationStorageError("artifact reference escapes its run") from exc
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise InvestigationStorageError("artifact is unavailable") from exc
        if sha256_bytes(raw) != reference.get("sha256"):
            raise InvestigationStorageError("artifact hash verification failed")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise InvestigationStorageError("artifact JSON is invalid") from exc
        if not isinstance(payload, dict):
            raise InvestigationStorageError("artifact must be an object")
        return payload


__all__ = [
    "InvestigationBusyError",
    "InvestigationNotFoundError",
    "InvestigationStorageError",
    "InvestigationStore",
]
