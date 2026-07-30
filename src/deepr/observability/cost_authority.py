"""Persistent cost-state discovery, provenance, and artifact identity."""

import hashlib
import json
import os
import sqlite3
import tomllib
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite
from pathlib import Path
from uuid import uuid4

from filelock import FileLock
from filelock import Timeout as FileLockTimeout

from deepr.observability.strict_json import loads_strict_json_object as _loads_strict_json
from deepr.utils.atomic_io import atomic_write_text

_ACCOUNTING_SOURCE_REGISTRY = "accounting_sources.jsonl"
_ACCOUNTING_SOURCE_REQUIRED = "accounting_sources.required.json"
_COST_STATE_FILE = "cost_state.json"
_SPEND_CAP_ENV_ARTIFACT = "spend_caps.env"
_CHECKOUT_DISCOVERY_ARTIFACT = "checkout.root"
_ACCOUNTING_SOURCE_ARTIFACTS = frozenset(
    {
        "cost_ledger.jsonl",
        "research_reservations.db",
        _SPEND_CAP_ENV_ARTIFACT,
        _CHECKOUT_DISCOVERY_ARTIFACT,
    }
)
_ACCOUNTING_SOURCE_SCHEMA_VERSION = 1
_SPEND_CAP_SOURCE_SCHEMA_VERSION = 2
_ARTIFACT_IDENTITY_SCHEMA_VERSION = 3
_SPEND_CAP_KEYS = frozenset({"per_job", "daily", "weekly", "monthly"})
_COST_STATE_SCHEMA_VERSION = 2
_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


class CostLedgerLockTimeout(TimeoutError):
    """A bounded cost-ledger lock attempt expired."""


class CostLedgerReadError(RuntimeError):
    """Canonical cost authority could not be read safely."""


class CostLedgerDurabilityError(RuntimeError):
    """A required cost-authority flush could not be confirmed durable."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _canonical_home_cost_data_dir() -> Path:
    """Return the home-anchored cost authority without consulting overrides."""
    try:
        target = Path.home() / ".deepr" / "costs"
    except (OSError, RuntimeError) as exc:
        raise ValueError("cost data home path is unavailable") from exc
    if not target.is_absolute():
        raise ValueError("cost data home path must be absolute")
    return target


def default_cost_data_dir() -> Path:
    """Resolve the cost-data directory.

    Honors DEEPR_COST_DATA_DIR so deployments can relocate cost state and -
    critically - so the test suite can isolate itself. Without the override,
    every process uses ~/.deepr/costs regardless of its current directory.
    Legacy source-checkout ledgers remain strict read-only siblings so their
    spend is still counted, but they can no longer split new reservations or
    writes across working directories.
    """
    base = os.environ.get("DEEPR_COST_DATA_DIR", "").strip()
    if base:
        configured = Path(base)
        if not configured.is_absolute():
            raise ValueError("DEEPR_COST_DATA_DIR must be an absolute path")
        return configured
    return _canonical_home_cost_data_dir()


def uses_canonical_home_cost_data_dir() -> bool:
    """Return whether the configured cost root is the canonical home root.

    An explicit override that names the same canonical directory must not turn
    off legacy accounting discovery. Treating the spelling of the environment
    variable as authority previously let the same path produce different spend
    totals.
    """
    try:
        return default_cost_data_dir().resolve() == _canonical_home_cost_data_dir().resolve()
    except OSError as exc:
        raise CostLedgerReadError("cost data authority paths cannot be resolved") from exc


def _cost_state_path() -> Path:
    return default_cost_data_dir() / _COST_STATE_FILE


@dataclass(frozen=True)
class _CostStateIdentity:
    cost_state_id: str
    created_at: str
    registry_required: bool
    registry_size_bytes: int
    registry_prefix_sha256: str


def _validated_hex_text(value: object, *, length: int, message: str) -> str:
    if not isinstance(value, str) or len(value) != length:
        raise CostLedgerReadError(message)
    try:
        int(value, 16)
    except ValueError as exc:
        raise CostLedgerReadError(message) from exc
    return value


def _validated_state_timestamp(value: object) -> str:
    if not isinstance(value, str):
        raise CostLedgerReadError("cost-state identity timestamp is invalid")
    try:
        _validated_timestamp(value)
    except ValueError as exc:
        raise CostLedgerReadError("cost-state identity timestamp is invalid") from exc
    return value


def _validated_state_registry_anchor(document: dict[str, object]) -> tuple[bool, int, str]:
    required = document.get("registry_required")
    size = document.get("registry_size_bytes")
    if not isinstance(required, bool):
        raise CostLedgerReadError("cost-state registry requirement is invalid")
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise CostLedgerReadError("cost-state registry size is invalid")
    fingerprint = _validated_hex_text(
        document.get("registry_prefix_sha256"),
        length=64,
        message="cost-state registry fingerprint is invalid",
    )
    if not required and (size != 0 or fingerprint != _EMPTY_SHA256):
        raise CostLedgerReadError("uninitialized cost-state registry anchor is invalid")
    return required, size, fingerprint


def _parse_cost_state(document: object) -> _CostStateIdentity:
    expected = {
        "schema_version",
        "cost_state_id",
        "created_at",
        "registry_required",
        "registry_size_bytes",
        "registry_prefix_sha256",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise CostLedgerReadError("cost-state identity is malformed")
    if document.get("schema_version") != _COST_STATE_SCHEMA_VERSION:
        raise CostLedgerReadError("cost-state identity schema is unsupported")
    state_id = _validated_hex_text(
        document.get("cost_state_id"),
        length=32,
        message="cost-state identity is invalid",
    )
    created_at = _validated_state_timestamp(document.get("created_at"))
    registry_required, registry_size_bytes, registry_prefix_sha256 = _validated_state_registry_anchor(document)
    return _CostStateIdentity(
        cost_state_id=state_id,
        created_at=created_at,
        registry_required=registry_required,
        registry_size_bytes=registry_size_bytes,
        registry_prefix_sha256=registry_prefix_sha256,
    )


def _cost_state_document(state: _CostStateIdentity) -> dict[str, object]:
    return {
        "schema_version": _COST_STATE_SCHEMA_VERSION,
        "cost_state_id": state.cost_state_id,
        "created_at": state.created_at,
        "registry_required": state.registry_required,
        "registry_size_bytes": state.registry_size_bytes,
        "registry_prefix_sha256": state.registry_prefix_sha256,
    }


def _read_cost_state_unlocked(path: Path) -> _CostStateIdentity:
    return _parse_cost_state(_loads_strict_json(path.read_text(encoding="utf-8")))


def _write_cost_state_unlocked(path: Path, state: _CostStateIdentity) -> None:
    payload = json.dumps(
        _cost_state_document(state),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    atomic_write_text(path, payload + "\n", fsync=True)


def _current_cost_state() -> _CostStateIdentity:
    """Return the durable identity and registry anchor for this money root."""
    path = _cost_state_path()
    lock_path = path.with_name(f"{path.name}.lock")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(lock_path), timeout=5.0, thread_local=False):
            if path.exists():
                return _read_cost_state_unlocked(path)
            state = _CostStateIdentity(
                cost_state_id=uuid4().hex,
                created_at=_utc_now().isoformat(),
                registry_required=False,
                registry_size_bytes=0,
                registry_prefix_sha256=_EMPTY_SHA256,
            )
            with path.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(
                    json.dumps(
                        _cost_state_document(state),
                        sort_keys=True,
                        separators=(",", ":"),
                        allow_nan=False,
                    )
                    + "\n"
                )
                handle.flush()
                os.fsync(handle.fileno())
            return state
    except FileLockTimeout as exc:
        raise CostLedgerLockTimeout("cost-state identity lock timed out") from exc
    except CostLedgerReadError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise CostLedgerDurabilityError("cost-state identity is unavailable") from exc


def current_cost_state_id() -> str:
    """Return the durable identity bound to the configured money-state root."""
    state = _current_cost_state()
    if state.registry_required:
        if not _read_accounting_source_required():
            raise CostLedgerReadError("required accounting source marker is missing")
        registry = _accounting_source_registry_path()
        if not registry.is_file():
            raise CostLedgerReadError("required accounting source registry is missing")
        _validate_registry_anchor(registry, state=state)
    return state.cost_state_id


def _mark_registry_required() -> None:
    path = _cost_state_path()
    try:
        with FileLock(str(path.with_name(f"{path.name}.lock")), timeout=5.0, thread_local=False):
            state = _read_cost_state_unlocked(path)
            if state.registry_required:
                return
            _write_cost_state_unlocked(
                path,
                _CostStateIdentity(
                    cost_state_id=state.cost_state_id,
                    created_at=state.created_at,
                    registry_required=True,
                    registry_size_bytes=0,
                    registry_prefix_sha256=_EMPTY_SHA256,
                ),
            )
    except FileLockTimeout as exc:
        raise CostLedgerLockTimeout("cost-state identity lock timed out") from exc
    except CostLedgerReadError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise CostLedgerDurabilityError("cost-state registry requirement could not be persisted") from exc


def _source_checkout_cost_data_dir() -> Path | None:
    """Return the stable legacy cost root for an editable source checkout."""
    try:
        root = Path(__file__).resolve().parents[3]
    except (IndexError, OSError):
        return None
    if not _is_deepr_checkout(root):
        return None
    return root / "data" / "costs"


def _is_deepr_checkout(root: Path) -> bool:
    """Accept only a checkout whose package metadata identifies Deepr."""
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file() or not (root / "src" / "deepr").is_dir():
        return False
    try:
        with pyproject.open("rb") as handle:
            project = tomllib.load(handle).get("project", {})
    except (OSError, tomllib.TOMLDecodeError):
        return False
    return isinstance(project, dict) and project.get("name") == "deepr-research"


def _cwd_checkout_cost_data_dir() -> Path | None:
    """Find a validated checkout when installed code runs below its root."""
    try:
        current = Path.cwd().resolve()
    except OSError:
        return None
    for root in (current, *current.parents):
        if _is_deepr_checkout(root):
            return root / "data" / "costs"
    return None


def _discover_checkout_cost_data_dirs() -> tuple[Path, ...]:
    """Discover validated checkouts without making CWD a write authority."""
    candidates = (_source_checkout_cost_data_dir(), _cwd_checkout_cost_data_dir())
    roots: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate is None:
            continue
        try:
            identity = candidate.resolve()
        except OSError as exc:
            raise CostLedgerReadError("checkout cost authority cannot be resolved") from exc
        if identity not in seen:
            seen.add(identity)
            roots.append(candidate)
    return tuple(roots)


def _accounting_source_registry_path() -> Path:
    return default_cost_data_dir() / _ACCOUNTING_SOURCE_REGISTRY


def _accounting_source_required_path() -> Path:
    return default_cost_data_dir() / _ACCOUNTING_SOURCE_REQUIRED


def _read_accounting_source_required() -> bool:
    marker = _accounting_source_required_path()
    if not marker.exists():
        if _current_cost_state().registry_required:
            raise CostLedgerReadError("required accounting source marker is missing")
        return False
    try:
        document = _loads_strict_json(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise CostLedgerReadError("accounting source requirement marker is unreadable") from exc
    if set(document) != {"schema_version", "cost_state_id", "registry"}:
        raise CostLedgerReadError("accounting source requirement marker is malformed")
    if document.get("schema_version") != _ACCOUNTING_SOURCE_SCHEMA_VERSION:
        raise CostLedgerReadError("accounting source requirement marker schema is unsupported")
    if document.get("registry") != _ACCOUNTING_SOURCE_REGISTRY:
        raise CostLedgerReadError("accounting source requirement marker is invalid")
    if document.get("cost_state_id") != _current_cost_state().cost_state_id:
        raise CostLedgerReadError("accounting source requirement belongs to another cost state")
    return True


def _ensure_accounting_source_required() -> None:
    if _read_accounting_source_required():
        _mark_registry_required()
        return
    marker = _accounting_source_required_path()
    document = {
        "schema_version": _ACCOUNTING_SOURCE_SCHEMA_VERSION,
        "cost_state_id": current_cost_state_id(),
        "registry": _ACCOUNTING_SOURCE_REGISTRY,
    }
    try:
        with marker.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        if not _read_accounting_source_required():
            raise CostLedgerReadError("accounting source requirement marker could not be confirmed")
    except OSError as exc:
        raise CostLedgerDurabilityError("accounting source requirement marker could not be persisted") from exc
    _mark_registry_required()


def _checkout_root_for_cost_data_dir(root: Path) -> Path | None:
    """Recover a validated checkout from its legacy ``data/costs`` root."""
    try:
        resolved = root.resolve()
        checkout = resolved.parents[1]
    except (IndexError, OSError):
        return None
    if resolved != checkout / "data" / "costs" or not _is_deepr_checkout(checkout):
        return None
    return checkout


def _cost_source_artifact_path(root: Path, artifact: str) -> Path:
    if artifact == _SPEND_CAP_ENV_ARTIFACT:
        checkout = _checkout_root_for_cost_data_dir(root)
        if checkout is None:
            raise CostLedgerReadError("registered spend-cap source is not a validated Deepr checkout")
        return checkout / ".env"
    if artifact == _CHECKOUT_DISCOVERY_ARTIFACT:
        return root
    return root / artifact


def _normalized_registered_root(value: object) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise CostLedgerReadError("accounting source registry contains an invalid root")
    root = Path(value)
    if not root.is_absolute():
        raise CostLedgerReadError("accounting source registry contains a relative root")
    try:
        return root.resolve()
    except OSError as exc:
        raise CostLedgerReadError("accounting source registry root cannot be resolved") from exc


def _normalized_spend_cap_limits(value: object) -> dict[str, float]:
    if not isinstance(value, dict) or not value or not set(value).issubset(_SPEND_CAP_KEYS):
        raise CostLedgerReadError("spend-cap registry contains invalid limits")
    normalized: dict[str, float] = {}
    for key, raw in value.items():
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise CostLedgerReadError("spend-cap registry contains invalid limits")
        numeric = float(raw)
        if not isfinite(numeric) or numeric < 0:
            raise CostLedgerReadError("spend-cap registry contains invalid limits")
        normalized[str(key)] = numeric
    return normalized


def _spend_cap_policy_sha256(limits: dict[str, float]) -> str:
    payload = json.dumps(limits, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _normalized_artifact_identity(artifact: str, value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise CostLedgerReadError("accounting source registry contains an invalid artifact identity")
    if artifact == "cost_ledger.jsonl":
        if set(value) != {"size_bytes", "prefix_sha256"}:
            raise CostLedgerReadError("cost ledger identity is malformed")
        size = value.get("size_bytes")
        fingerprint = value.get("prefix_sha256")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise CostLedgerReadError("cost ledger identity size is invalid")
    elif artifact == "research_reservations.db":
        if set(value) != {"max_rowid", "row_count", "rows_sha256"}:
            raise CostLedgerReadError("reservation identity is malformed")
        max_rowid = value.get("max_rowid")
        row_count = value.get("row_count")
        fingerprint = value.get("rows_sha256")
        if (
            isinstance(max_rowid, bool)
            or not isinstance(max_rowid, int)
            or max_rowid < 0
            or isinstance(row_count, bool)
            or not isinstance(row_count, int)
            or row_count < 0
            or row_count > max_rowid
        ):
            raise CostLedgerReadError("reservation identity bounds are invalid")
    else:
        raise CostLedgerReadError("artifact identity cannot describe this source")
    if not isinstance(fingerprint, str) or len(fingerprint) != 64:
        raise CostLedgerReadError("artifact identity fingerprint is invalid")
    try:
        int(fingerprint, 16)
    except ValueError as exc:
        raise CostLedgerReadError("artifact identity fingerprint is invalid") from exc
    return dict(value)


def _accounting_record_expected_fields(schema_version: object) -> set[str]:
    expected_fields = {"schema_version", "registered_at", "root", "artifact"}
    if schema_version == _SPEND_CAP_SOURCE_SCHEMA_VERSION:
        expected_fields.update({"policy_sha256", "limits"})
    elif schema_version == _ARTIFACT_IDENTITY_SCHEMA_VERSION:
        expected_fields.add("identity")
    elif schema_version != _ACCOUNTING_SOURCE_SCHEMA_VERSION:
        raise CostLedgerReadError("accounting source registry schema is unsupported")
    return expected_fields


def _validated_record_artifact(schema_version: object, artifact: object) -> str:
    if artifact not in _ACCOUNTING_SOURCE_ARTIFACTS:
        raise CostLedgerReadError("accounting source registry contains an unknown artifact")
    if schema_version == _ACCOUNTING_SOURCE_SCHEMA_VERSION and artifact == _SPEND_CAP_ENV_ARTIFACT:
        raise CostLedgerReadError("spend-cap registry record lacks immutable policy provenance")
    if schema_version == _SPEND_CAP_SOURCE_SCHEMA_VERSION and artifact != _SPEND_CAP_ENV_ARTIFACT:
        raise CostLedgerReadError("accounting source registry contains an invalid policy artifact")
    if schema_version == _ARTIFACT_IDENTITY_SCHEMA_VERSION and artifact == _SPEND_CAP_ENV_ARTIFACT:
        raise CostLedgerReadError("spend-cap source cannot use artifact identity schema")
    return str(artifact)


def _accounting_record_payload(
    schema_version: object,
    artifact: str,
    document: dict[str, object],
) -> tuple[dict[str, float] | None, dict[str, object] | None]:
    if schema_version == _SPEND_CAP_SOURCE_SCHEMA_VERSION:
        limits = _normalized_spend_cap_limits(document.get("limits"))
        fingerprint = document.get("policy_sha256")
        if not isinstance(fingerprint, str) or fingerprint != _spend_cap_policy_sha256(limits):
            raise CostLedgerReadError("spend-cap registry policy fingerprint is invalid")
        return limits, None
    if schema_version == _ARTIFACT_IDENTITY_SCHEMA_VERSION:
        return None, _normalized_artifact_identity(artifact, document.get("identity"))
    return None, None


def _parse_accounting_source_record(
    line: str,
) -> tuple[Path, str, dict[str, float] | None, dict[str, object] | None]:
    document = _loads_strict_json(line)
    schema_version = document.get("schema_version")
    if set(document) != _accounting_record_expected_fields(schema_version):
        raise CostLedgerReadError("accounting source registry contains a malformed record")
    artifact = _validated_record_artifact(schema_version, document.get("artifact"))
    registered_at = document.get("registered_at")
    if not isinstance(registered_at, str):
        raise CostLedgerReadError("accounting source registry contains an invalid timestamp")
    _validated_timestamp(registered_at)
    limits, identity = _accounting_record_payload(schema_version, artifact, document)
    return _normalized_registered_root(document.get("root")), artifact, limits, identity


def _read_registered_cost_source_records() -> list[tuple[Path, str, dict[str, float] | None, dict[str, object] | None]]:
    """Read every append-only registry record under canonical home authority."""
    if not uses_canonical_home_cost_data_dir():
        return []
    registry = _accounting_source_registry_path()
    if not registry.exists():
        if _read_accounting_source_required():
            raise CostLedgerReadError("required accounting source registry is missing")
        return []
    _validate_registry_anchor(registry)
    _ensure_accounting_source_required()
    records: list[tuple[Path, str, dict[str, float] | None, dict[str, object] | None]] = []
    try:
        with registry.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                records.append(_parse_accounting_source_record(line))
    except CostLedgerReadError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise CostLedgerReadError("accounting source registry is unreadable") from exc
    if not records:
        raise CostLedgerReadError("accounting source registry is empty")
    _advance_registry_anchor(registry)
    return records


def _read_registered_cost_sources() -> dict[Path, set[str]]:
    """Read the append-only home registry strictly."""
    sources: dict[Path, set[str]] = {}
    for root, artifact, _limits, _identity in _read_registered_cost_source_records():
        sources.setdefault(root, set()).add(artifact)
    return sources


def _sha256_file_prefix(path: Path, size_bytes: int) -> str:
    digest = hashlib.sha256()
    remaining = size_bytes
    try:
        with path.open("rb") as handle:
            while remaining:
                chunk = handle.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise CostLedgerReadError("registered cost artifact is shorter than its identity")
                digest.update(chunk)
                remaining -= len(chunk)
    except CostLedgerReadError:
        raise
    except OSError as exc:
        raise CostLedgerReadError("registered cost artifact cannot be read") from exc
    return digest.hexdigest()


def _validate_registry_anchor(registry: Path, *, state: _CostStateIdentity | None = None) -> None:
    state = state or _current_cost_state()
    if not state.registry_required:
        return
    try:
        current_size = registry.stat().st_size
    except OSError as exc:
        raise CostLedgerReadError("required accounting source registry cannot be inspected") from exc
    if current_size < state.registry_size_bytes:
        raise CostLedgerReadError("accounting source registry was truncated or replaced")
    if _sha256_file_prefix(registry, state.registry_size_bytes) != state.registry_prefix_sha256:
        raise CostLedgerReadError("accounting source registry was truncated or replaced")


def _advance_registry_anchor(registry: Path) -> None:
    state_path = _cost_state_path()
    try:
        with FileLock(
            str(state_path.with_name(f"{state_path.name}.lock")),
            timeout=5.0,
            thread_local=False,
        ):
            state = _read_cost_state_unlocked(state_path)
            current_size = registry.stat().st_size
            if current_size < state.registry_size_bytes:
                raise CostLedgerReadError("accounting source registry was truncated or replaced")
            if _sha256_file_prefix(registry, state.registry_size_bytes) != state.registry_prefix_sha256:
                raise CostLedgerReadError("accounting source registry was truncated or replaced")
            current_fingerprint = _sha256_file_prefix(registry, current_size)
            if (
                state.registry_required
                and current_size == state.registry_size_bytes
                and current_fingerprint == state.registry_prefix_sha256
            ):
                return
            _write_cost_state_unlocked(
                state_path,
                _CostStateIdentity(
                    cost_state_id=state.cost_state_id,
                    created_at=state.created_at,
                    registry_required=True,
                    registry_size_bytes=current_size,
                    registry_prefix_sha256=current_fingerprint,
                ),
            )
    except FileLockTimeout as exc:
        raise CostLedgerLockTimeout("cost-state identity lock timed out") from exc
    except CostLedgerReadError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise CostLedgerDurabilityError("accounting source registry anchor could not be persisted") from exc


def _ledger_artifact_identity(path: Path) -> dict[str, object]:
    try:
        size_bytes = path.stat().st_size
    except OSError as exc:
        raise CostLedgerReadError("cost ledger identity cannot be inspected") from exc
    return {
        "size_bytes": size_bytes,
        "prefix_sha256": _sha256_file_prefix(path, size_bytes),
    }


def _reservation_artifact_identity(path: Path, *, max_rowid: int | None = None) -> dict[str, object]:
    try:
        resolved = path.resolve()
        uri = f"{resolved.as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=5.0)) as connection:
            if max_rowid is None:
                rows = connection.execute(
                    "SELECT rowid, reservation_id, job_id, reserved_cost, created_at "
                    "FROM research_cost_reservations ORDER BY rowid"
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT rowid, reservation_id, job_id, reserved_cost, created_at "
                    "FROM research_cost_reservations WHERE rowid <= ? ORDER BY rowid",
                    (max_rowid,),
                ).fetchall()
    except (OSError, sqlite3.Error) as exc:
        raise CostLedgerReadError("reservation identity cannot be read") from exc
    normalized: list[list[object]] = []
    observed_max = 0
    for rowid, reservation_id, job_id, reserved_cost, created_at in rows:
        if isinstance(rowid, bool) or not isinstance(rowid, int) or rowid <= 0:
            raise CostLedgerReadError("reservation identity contains an invalid row ID")
        cost = _validated_cost(reserved_cost, field_name="reserved_cost")
        if not isinstance(reservation_id, str) or not isinstance(job_id, str) or not isinstance(created_at, str):
            raise CostLedgerReadError("reservation identity contains invalid immutable fields")
        normalized.append([rowid, reservation_id, job_id, cost, created_at])
        observed_max = max(observed_max, rowid)
    if max_rowid is not None:
        observed_max = max_rowid
    payload = json.dumps(normalized, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return {
        "max_rowid": observed_max,
        "row_count": len(normalized),
        "rows_sha256": hashlib.sha256(payload).hexdigest(),
    }


def _artifact_identity(path: Path, artifact: str) -> dict[str, object]:
    if artifact == "cost_ledger.jsonl":
        return _ledger_artifact_identity(path)
    if artifact == "research_reservations.db":
        return _reservation_artifact_identity(path)
    raise ValueError("unsupported accounting identity artifact")


def _validate_artifact_identity(path: Path, artifact: str, identity: dict[str, object]) -> None:
    if artifact == "cost_ledger.jsonl":
        size_bytes = identity["size_bytes"]
        if isinstance(size_bytes, bool) or not isinstance(size_bytes, int):
            raise CostLedgerReadError("cost ledger identity size is invalid")
        try:
            current_size = path.stat().st_size
        except OSError as exc:
            raise CostLedgerReadError("registered cost ledger cannot be inspected") from exc
        if current_size < size_bytes or _sha256_file_prefix(path, size_bytes) != identity["prefix_sha256"]:
            raise CostLedgerReadError("registered cost ledger was truncated or replaced")
        return
    if artifact == "research_reservations.db":
        max_rowid = identity["max_rowid"]
        if isinstance(max_rowid, bool) or not isinstance(max_rowid, int):
            raise CostLedgerReadError("reservation identity bound is invalid")
        observed = _reservation_artifact_identity(path, max_rowid=max_rowid)
        if observed["row_count"] != identity["row_count"] or observed["rows_sha256"] != identity["rows_sha256"]:
            raise CostLedgerReadError("registered reservation state was truncated or replaced")
        return
    raise ValueError("unsupported accounting identity artifact")


def _resolved_registration_root(root: Path, artifact: str) -> Path:
    if artifact not in _ACCOUNTING_SOURCE_ARTIFACTS:
        raise ValueError("unsupported accounting source artifact")
    if artifact in {_SPEND_CAP_ENV_ARTIFACT, _CHECKOUT_DISCOVERY_ARTIFACT}:
        raise ValueError("artifact requires dedicated provenance registration")
    try:
        return root.resolve()
    except OSError as exc:
        raise CostLedgerReadError("accounting source root cannot be resolved") from exc


def _validated_artifact_observation(
    artifact_path: Path,
    artifact: str,
    matching: list[dict[str, object] | None],
) -> dict[str, object] | None:
    if not artifact_path.is_file():
        if matching:
            if artifact == "cost_ledger.jsonl":
                raise CostLedgerReadError("registered cost ledger is missing")
            raise CostLedgerReadError("registered reservation state is missing")
        return None
    for identity in matching:
        if identity is not None:
            _validate_artifact_identity(artifact_path, artifact, identity)
    return _artifact_identity(artifact_path, artifact)


def _register_cost_source(root: Path, artifact: str) -> None:
    """Validate and advance one monotonic cost-artifact identity."""
    if not uses_canonical_home_cost_data_dir():
        return
    resolved_root = _resolved_registration_root(root, artifact)
    artifact_path = _cost_source_artifact_path(resolved_root, artifact)
    registry = _accounting_source_registry_path()
    try:
        registry.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(registry.with_name(f"{registry.name}.lock")), timeout=5.0, thread_local=False):
            records = _read_registered_cost_source_records()
            matching = [
                identity
                for record_root, record_artifact, _limits, identity in records
                if record_root == resolved_root and record_artifact == artifact
            ]
            current = _validated_artifact_observation(artifact_path, artifact, matching)
            if current is None:
                return
            if current in matching:
                with registry.open("a+b") as handle:
                    os.fsync(handle.fileno())
                _advance_registry_anchor(registry)
                return
            record = {
                "schema_version": _ARTIFACT_IDENTITY_SCHEMA_VERSION,
                "registered_at": _utc_now().isoformat(),
                "root": str(resolved_root),
                "artifact": artifact,
                "identity": current,
            }
            _ensure_accounting_source_required()
            with registry.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            _advance_registry_anchor(registry)
    except FileLockTimeout as exc:
        raise CostLedgerLockTimeout("accounting source registry lock timed out") from exc
    except CostLedgerReadError:
        raise
    except OSError as exc:
        raise CostLedgerDurabilityError("accounting source registry could not be persisted") from exc


def _register_checkout_root(root: Path) -> None:
    """Persist a validated checkout before any cost artifact exists."""
    if not uses_canonical_home_cost_data_dir():
        return
    try:
        resolved_root = root.resolve()
    except OSError as exc:
        raise CostLedgerReadError("checkout cost source cannot be resolved") from exc
    registry = _accounting_source_registry_path()
    try:
        registry.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(registry.with_name(f"{registry.name}.lock")), timeout=5.0, thread_local=False):
            records = _read_registered_cost_source_records()
            if any(
                record_root == resolved_root and artifact == _CHECKOUT_DISCOVERY_ARTIFACT
                for record_root, artifact, _limits, _identity in records
            ):
                _advance_registry_anchor(registry)
                return
            record = {
                "schema_version": _ACCOUNTING_SOURCE_SCHEMA_VERSION,
                "registered_at": _utc_now().isoformat(),
                "root": str(resolved_root),
                "artifact": _CHECKOUT_DISCOVERY_ARTIFACT,
            }
            _ensure_accounting_source_required()
            with registry.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            _advance_registry_anchor(registry)
    except FileLockTimeout as exc:
        raise CostLedgerLockTimeout("accounting source registry lock timed out") from exc
    except CostLedgerReadError:
        raise
    except OSError as exc:
        raise CostLedgerDurabilityError("checkout cost provenance could not be persisted") from exc


def registered_cost_artifact_paths(artifact: str) -> tuple[Path, ...]:
    """Return every persisted legacy artifact path required for accounting."""
    if artifact not in _ACCOUNTING_SOURCE_ARTIFACTS:
        raise ValueError("unsupported accounting source artifact")
    return tuple(
        _cost_source_artifact_path(root, artifact)
        for root, artifacts in sorted(_read_registered_cost_sources().items(), key=lambda item: str(item[0]).casefold())
        if artifact in artifacts
    )


def observe_cost_artifact(path: Path) -> None:
    """Validate and advance high-water identity for a money-state artifact."""
    if path.name not in {"cost_ledger.jsonl", "research_reservations.db"}:
        raise ValueError("unsupported accounting identity artifact")
    _register_cost_source(path.parent, path.name)


def well_known_spend_cap_env_paths() -> tuple[Path, ...]:
    """Return validated checkout env files that can only tighten paid caps."""
    if not uses_canonical_home_cost_data_dir():
        return ()
    registered = set(registered_cost_artifact_paths(_SPEND_CAP_ENV_ARTIFACT))
    roots = [*_discover_checkout_cost_data_dirs(), *_read_registered_cost_sources()]
    candidates: list[Path] = []
    for root in roots:
        checkout = _checkout_root_for_cost_data_dir(root)
        if checkout is not None:
            candidates.append(checkout / ".env")
    candidates.extend(registered)

    unique: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        try:
            identity = candidate.resolve()
            exists = candidate.is_file()
        except OSError as exc:
            raise CostLedgerReadError("spend-cap source cannot be inspected") from exc
        if identity in registered and not exists:
            raise CostLedgerReadError("registered spend-cap source is missing")
        if exists and identity not in seen:
            seen.add(identity)
            unique.append(candidate)
    return tuple(unique)


def _effective_spend_cap_policy(
    current: dict[str, float],
    previous: list[dict[str, float]],
) -> dict[str, float]:
    if not current:
        if previous:
            raise CostLedgerReadError("registered spend-cap source no longer declares its policy")
        return {}
    historical: dict[str, float] = {}
    for policy in previous:
        for key, value in policy.items():
            historical[key] = min(historical.get(key, value), value)
    if not set(historical).issubset(current):
        raise CostLedgerReadError("registered spend-cap source removed a binding limit")
    if any(current[key] > ceiling for key, ceiling in historical.items()):
        raise CostLedgerReadError("registered spend-cap source widened a binding limit")
    return {key: min(value, historical.get(key, value)) for key, value in current.items()}


def register_spend_cap_env_source(path: Path, limits: dict[str, float]) -> dict[str, float]:
    """Persist immutable cap provenance and return its monotonic ceilings."""
    try:
        resolved = path.resolve()
    except OSError as exc:
        raise CostLedgerReadError("spend-cap source cannot be resolved") from exc
    checkout = resolved.parent
    if resolved.name != ".env" or not _is_deepr_checkout(checkout):
        raise CostLedgerReadError("spend-cap source is not a validated Deepr checkout env")
    root = (checkout / "data" / "costs").resolve()
    current = _normalized_spend_cap_limits(limits) if limits else {}
    registry = _accounting_source_registry_path()
    try:
        registry.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(registry.with_name(f"{registry.name}.lock")), timeout=5.0, thread_local=False):
            records = _read_registered_cost_source_records()
            previous = [
                record_limits
                for record_root, artifact, record_limits, _identity in records
                if record_root == root and artifact == _SPEND_CAP_ENV_ARTIFACT and record_limits is not None
            ]
            effective = _effective_spend_cap_policy(current, previous)
            if not current:
                return effective
            if current in previous:
                _advance_registry_anchor(registry)
                return effective

            record = {
                "schema_version": _SPEND_CAP_SOURCE_SCHEMA_VERSION,
                "registered_at": _utc_now().isoformat(),
                "root": str(root),
                "artifact": _SPEND_CAP_ENV_ARTIFACT,
                "policy_sha256": _spend_cap_policy_sha256(current),
                "limits": current,
            }
            _ensure_accounting_source_required()
            with registry.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            _advance_registry_anchor(registry)
            return effective
    except FileLockTimeout as exc:
        raise CostLedgerLockTimeout("accounting source registry lock timed out") from exc
    except CostLedgerReadError:
        raise
    except OSError as exc:
        raise CostLedgerDurabilityError("spend-cap provenance could not be persisted") from exc


def well_known_cost_data_dirs() -> tuple[Path, ...]:
    """Return stable canonical and legacy roots used for strict accounting."""
    if not uses_canonical_home_cost_data_dir():
        return (default_cost_data_dir(),)
    candidates = [default_cost_data_dir()]
    discovered = _discover_checkout_cost_data_dirs()
    for root in discovered:
        _register_checkout_root(root)
        for artifact in ("cost_ledger.jsonl", "research_reservations.db"):
            _register_cost_source(root, artifact)
        candidates.append(root)
    registered = _read_registered_cost_sources()
    for root, artifacts in registered.items():
        if _CHECKOUT_DISCOVERY_ARTIFACT in artifacts:
            for artifact in ("cost_ledger.jsonl", "research_reservations.db"):
                _register_cost_source(root, artifact)
    candidates.extend(registered)
    unique: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        try:
            identity = candidate.resolve()
        except OSError:
            identity = candidate.absolute()
        if identity not in seen:
            seen.add(identity)
            unique.append(candidate)
    return tuple(unique)


def well_known_ledger_paths() -> tuple[Path, ...]:
    """Return stable ledger paths without creating files or directories."""
    return tuple(root / "cost_ledger.jsonl" for root in well_known_cost_data_dirs())


def _validated_cost(value: object, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a finite non-negative number")
    numeric = float(value)
    if not isfinite(numeric) or numeric < 0:
        raise ValueError(f"{field_name} must be a finite non-negative number")
    return numeric


def _validated_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO-8601 string")
    timestamp = datetime.fromisoformat(value)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("timestamp must include a UTC offset")
    return timestamp
