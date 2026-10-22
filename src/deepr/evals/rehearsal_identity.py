"""Read-only execution identity for the local four-arm rehearsal.

Paths and Git provenance are recorded elsewhere. This boundary compares source
bytes, runtime and dependency versions; it does not attest third-party bytes or
make local model output deterministic.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Callable
from importlib import metadata
from pathlib import Path
from typing import Any

IDENTITY_SCHEMA = "deepr-rehearsal-execution-identity-v1"


class RehearsalIdentityError(ValueError):
    """Execution evidence changed or cannot be verified; never an ordinary model failure."""


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def execution_identity(package: Path | None = None) -> dict[str, Any]:
    """Bind the complete Python source inventory and observed environment."""
    root = package or Path(__file__).resolve().parents[1]
    modules = {
        path.relative_to(root).as_posix(): _digest(path)
        for path in sorted(root.rglob("*.py"))
        if "node_modules" not in path.relative_to(root).parts
    }
    if not modules:
        raise ValueError("rehearsal execution identity needs installed Python source files")
    checkout = root.parents[1]
    lock = None
    if (checkout / "src" / "deepr").resolve() == root.resolve():
        lock = {name: _digest(checkout / name) for name in ("uv.lock", "pyproject.toml")}
    distributions = sorted((str(dist.metadata["Name"]), dist.version) for dist in metadata.distributions())
    return {
        "schema_version": IDENTITY_SCHEMA,
        "module_sha256": modules,
        "python": {"implementation": sys.implementation.name, "version": sys.version},
        "distributions": [list(item) for item in distributions],
        "checkout_sha256": lock,
    }


def identity_sha256(identity: dict[str, Any]) -> str:
    """One stable digest for compact worker specs and receipts."""
    return hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def check_execution_identity(expected: str | None) -> str:
    """Check before launch; retain a typed integrity failure even if source is unreadable."""
    try:
        observed = identity_sha256(execution_identity())
    except (OSError, ValueError) as error:
        raise RehearsalIdentityError("rehearsal execution identity could not be read") from error
    if expected != observed:
        raise RehearsalIdentityError("rehearsal execution identity changed before worker launch")
    return observed


def execution_checks(workers: list[dict[str, Any]], expected: str) -> dict[str, bool | None]:
    """Past drift remains an integrity failure even if source bytes are restored."""
    try:
        check_execution_identity(expected)
        unchanged = not any(w.get("error_type") == "RehearsalIdentityError" for w in workers)
    except RehearsalIdentityError:
        unchanged = False
    identified = [w for w in workers if "execution_identity_sha256" in w or w.get("status") == "completed"]
    return {
        "execution_identity_unchanged": unchanged,
        "worker_execution_identity_matches": (
            all(w.get("execution_identity_sha256") == expected for w in identified) if identified else None
        ),
    }


def legacy_worker_code_matches(workers: list[dict[str, Any]], read: Callable[[], dict[str, str]]) -> bool | None:
    """Unreadable legacy evidence fails explicitly without preventing a final report."""
    try:
        expected = read()
    except OSError:
        return False
    reported = [w for w in workers if "module_sha256" in w]
    return all(w["module_sha256"] == expected for w in reported) if reported else None


def verify_resume_identity(run_root: Path, modules: dict[str, str]) -> dict[str, Any]:
    """Refuse changed or historical identities without probes or durable writes."""
    record = json.loads((run_root / "run.json").read_text(encoding="utf-8"))
    application = record.get("application", {}) if isinstance(record, dict) else {}
    if not isinstance(application, dict):
        raise ValueError("rehearsal application identity is malformed")
    saved = application.get("execution_identity")
    if not isinstance(saved, dict) or saved.get("schema_version") != IDENTITY_SCHEMA:
        raise ValueError("historical rehearsal has no execution identity; inspect it read-only and start a new run")
    if saved != execution_identity() or application.get("module_sha256") != modules:
        raise ValueError("rehearsal execution identity changed; start a new run root")
    summary = run_root / "summary.json"
    if summary.exists():
        checks = json.loads(summary.read_text(encoding="utf-8"))
        if any(
            checks.get(k) is False
            for k in (
                "execution_identity_unchanged",
                "worker_execution_identity_matches",
                "worker_code_matches_orchestrator",
            )
        ):
            raise ValueError("rehearsal recorded an execution identity failure; start a new run root")
    return saved
