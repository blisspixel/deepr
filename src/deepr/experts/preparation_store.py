"""Private offline preparation operations, not caller authentication or a sandbox.

Callers supply an explicit root and a trusted service-derived CallerScope. No
public interface, inference, acquisition or canonical expert state is touched.
Windows uses the existing optional pywin32 dependency lazily and fails closed
without it. Clean core-install Windows support is unqualified; docs/full brings
pywin32 transitively through docx2pdf. This module adds no dependency.
"""

from __future__ import annotations

import base64
import json
import os
import re
import stat
import uuid
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import islice
from pathlib import Path
from typing import Any

from filelock import FileLock

from deepr.experts.corpus_store import CorpusStore, content_hash
from deepr.experts.preparation_contracts import (
    CallerScope,
    FrozenPreparation,
    PreparationEnvelope,
    PreparationLimits,
    PreparationPacket,
    PreparationRequest,
    ProjectionManifest,
    canonical_bytes,
    freeze_packet,
    sha256,
)
from deepr.experts.preparation_permissions import (
    PreparationPermissions as _Protection,
)
from deepr.experts.preparation_permissions import (
    PreparationStoreError,
    StoreProtectionError,
)
from deepr.utils.atomic_io import append_jsonl_durable, atomic_write_bytes

TTL = timedelta(days=7)
# Offline prototype inspection ceilings, not source/semantic selection rules.
_MAX_INVENTORY = 256
_MARKER = b"deepr-private-preparation-store-v1\n"
_OPERATION = re.compile(r"^op_[0-9a-f]{32}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


class OperationDenied(PreparationStoreError):
    """Unknown or differently owned operation; no private payload is returned."""


class OperationExpired(OperationDenied):
    """Access TTL elapsed, whether or not reclamation succeeded."""


class OperationConflict(PreparationStoreError):
    """A claimed idempotency key was supplied with a changed envelope."""


class OperationNotReady(PreparationStoreError):
    """No immutable completed packet is available."""


@dataclass(frozen=True)
class ClaimReceipt:
    operation_id: str
    envelope_sha256: str
    status: str
    duplicate: bool
    envelope: PreparationEnvelope | None = None


class PreparationStore:
    """One operation namespace with seven-day access cutoff and bounded cleanup.

    CallerScope is trusted input from the service, not an HTTP identity proof.
    Logical owner checks do not isolate hostile code running as the same user.
    """

    def __init__(self, root: Path, *, clock: Callable[[], datetime] | None = None) -> None:
        if not root.is_absolute():
            raise StoreProtectionError("An explicit absolute private root is required")
        self.root = root.absolute()
        self.clock = clock or (lambda: datetime.now(UTC))
        self.protection = _Protection()
        self._ancestors(self.root)
        if self.root.exists():
            self.protection.verify(self.root, directory=True, protected=True)
            marker = self.root / "store.marker"
            if not marker.exists():
                raise StoreProtectionError("Unrelated existing storage root")
            self.protection.verify(marker, directory=False)
            if marker.read_bytes() != _MARKER:
                raise StoreProtectionError("Unrelated existing storage root")
        else:
            if not self.root.parent.is_dir():
                raise StoreProtectionError("Private root parent must already exist")
            self.protection.protect_new_directory(self.root)
            self._write(self.root / "store.marker", _MARKER)
        if not (self.root / "cleanup-cursor.json").exists():
            self._write_if_absent(self.root / "cleanup-cursor.json", canonical_bytes({"owner": 0, "entry": 0}))
        self._prepare_lock(self.root / "store.lock")
        self._prepare_lock(self.root / "tombstones.jsonl.append.lock")
        if not (self.root / "tombstones.jsonl").exists():
            self._write_if_absent(self.root / "tombstones.jsonl", b"")

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Store clock must be timezone aware")
        return value.astimezone(UTC)

    @staticmethod
    def _ancestors(path: Path) -> None:
        for ancestor in [path, *path.parents]:
            if ancestor.exists() or ancestor.is_symlink():
                info = ancestor.lstat()
                if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                    raise StoreProtectionError("Link or reparse ancestor refused")

    def _check(self, path: Path, *, directory: bool) -> None:
        if not path.is_relative_to(self.root):
            raise StoreProtectionError("Path escapes explicit store")
        self._ancestors(path)
        self.protection.verify(self.root, directory=True, protected=True)
        self.protection.verify(path, directory=directory, protected=directory)

    def _write(self, path: Path, data: bytes) -> None:
        self._check(path.parent, directory=True)
        if path.exists() or path.is_symlink():
            self._check(path, directory=False)
        atomic_write_bytes(path, data, fsync=True, fsync_parent=True, prepare_tempfile=self.protection.prepare_tempfile)
        self._check(path, directory=False)

    def _write_if_absent(self, path: Path, data: bytes) -> None:
        self._check(path.parent, directory=True)
        try:
            atomic_write_bytes(
                path,
                data,
                fsync=True,
                fsync_parent=True,
                overwrite=False,
                prepare_tempfile=self.protection.prepare_tempfile,
            )
        except FileExistsError:
            pass
        self._check(path, directory=False)

    def _prepare_lock(self, path: Path) -> None:
        if not path.exists():
            self._write_if_absent(path, b"")
        self._check(path, directory=False)

    @contextmanager
    def _lock(self) -> Iterator[None]:
        # Windows FileLock intentionally removes its path on release. Exclusive
        # no-replace preparation never swaps an inode held by another process.
        self._prepare_lock(self.root / "store.lock")
        # FileLock's Windows owner-only creation recipe also grants Administrators.
        # Inherit our verified owner/SYSTEM parent instead; POSIX needs mode0600.
        mode = 0o666 if os.name == "nt" else 0o600
        with FileLock(str(self.root / "store.lock"), mode=mode, timeout=10):
            self.protection.prepare_empty_lock(self.root / "store.lock")
            self._check(self.root / "store.lock", directory=False)
            yield

    @staticmethod
    def _inventory(path: Path) -> list[Path]:
        entries = list(islice(path.iterdir(), _MAX_INVENTORY + 1))
        if len(entries) > _MAX_INVENTORY:
            raise StoreProtectionError("Private inventory inspection capacity exhausted")
        return entries

    def _owner(self, owner: CallerScope, *, create: bool = False) -> Path:
        owner = CallerScope.model_validate(owner)
        for index, entry in enumerate(self.root.iterdir()):
            if index >= _MAX_INVENTORY:
                raise StoreProtectionError("Private root inventory exceeds inspection bound")
            if entry.name not in {
                "store.marker",
                "store.lock",
                "tombstones.jsonl",
                "tombstones.jsonl.append.lock",
                "cleanup-cursor.json",
            } and not _DIGEST.fullmatch(entry.name):
                raise StoreProtectionError("Unexpected private root entry")
        path = self.root / owner.namespace_sha256
        if not path.exists() and create:
            if sum(1 for _ in self.root.iterdir()) >= _MAX_INVENTORY:
                raise StoreProtectionError("Private root admission capacity exhausted")
            self.protection.protect_new_directory(path)
        if not path.exists():
            raise OperationDenied("Operation unavailable")
        self._check(path, directory=True)
        for index, entry in enumerate(path.iterdir()):
            if index >= _MAX_INVENTORY:
                raise StoreProtectionError("Owner inventory exceeds inspection bound")
            if not _OPERATION.fullmatch(entry.name) and not re.fullmatch(r"claim_[0-9a-f]{64}\.json", entry.name):
                raise StoreProtectionError("Unexpected owner namespace entry")
        return path

    def _operation(self, owner: CallerScope, operation_id: str) -> Path:
        if _OPERATION.fullmatch(operation_id) is None:
            raise OperationDenied("Operation unavailable")
        path = self._owner(owner) / operation_id
        if not path.exists():
            raise OperationDenied("Operation unavailable")
        self._check(path, directory=True)
        return path

    def _read_json(self, path: Path) -> dict[str, Any]:
        self._check(path, directory=False)
        value = json.loads(path.read_bytes())
        if not isinstance(value, dict):
            raise StoreProtectionError("Invalid operation metadata")
        return value

    def _state(
        self, owner: CallerScope, operation_id: str, *, allow_expired: bool = False
    ) -> tuple[Path, dict[str, Any]]:
        path = self._operation(owner, operation_id)
        for index, entry in enumerate(path.iterdir()):
            if index >= 20:
                raise StoreProtectionError("Operation inventory exceeds inspection bound")
            if entry.name not in {
                "state.json",
                "envelope.json",
                "binding.json",
                "limits.json",
                "content.json",
                "review.md",
                "graph.json",
                "projections.json",
                "events.jsonl",
                "events.jsonl.append.lock",
                "corpus",
                "capture.json",
            } and not re.fullmatch(r"[0-9a-f]{64}\.source", entry.name):
                raise StoreProtectionError("Unexpected operation entry")
        state = self._read_json(path / "state.json")
        if state["owner"] != owner.namespace_sha256 or state["operation_id"] != operation_id:
            raise OperationDenied("Operation unavailable")
        if not allow_expired and self._now() >= datetime.fromisoformat(state["expires_at"]):
            raise OperationExpired("Operation expired")
        return path, state

    def claim(
        self,
        owner: CallerScope,
        request: PreparationRequest,
        question: str,
        expert_revision: str,
        *,
        binding: Mapping[str, str],
        stored_position_ids: tuple[str, ...] = (),
        limits: PreparationLimits | None = None,
    ) -> ClaimReceipt:
        """Atomically claim once. Duplicates never return a payload or allowance."""
        if not binding or any(not isinstance(key, str) or not isinstance(value, str) for key, value in binding.items()):
            raise ValueError("Explicit service policy/model binding is required")
        admitted_limits = PreparationLimits() if limits is None else PreparationLimits.model_validate(limits)
        operation_id = "op_" + uuid.uuid4().hex
        envelope = PreparationEnvelope(
            operation_id=operation_id,
            owner=owner,
            request=request,
            question=question,
            expert_revision=expert_revision,
            stored_position_ids=stored_position_ids,
        )
        bound = envelope.model_dump(mode="json")
        del bound["operation_id"]
        envelope_hash = sha256(
            canonical_bytes(
                {"envelope": bound, "binding": dict(binding), "limits": admitted_limits.model_dump(mode="json")}
            )
        )
        with self._lock():
            namespace = self._owner(owner, create=True)
            claim_path = namespace / ("claim_" + sha256(request.request_id.encode()) + ".json")
            if claim_path.exists():
                claimed = self._read_json(claim_path)
                if claimed["envelope_sha256"] != envelope_hash:
                    raise OperationConflict("Request key binds a different envelope")
                _, state = self._state(owner, claimed["operation_id"], allow_expired=True)
                status = "expired" if self._now() >= datetime.fromisoformat(state["expires_at"]) else state["status"]
                return ClaimReceipt(claimed["operation_id"], envelope_hash, status, True)
            if sum(1 for _ in namespace.iterdir()) + 2 > _MAX_INVENTORY:
                raise StoreProtectionError("Owner admission capacity exhausted")
            path = namespace / operation_id
            self.protection.protect_new_directory(path)
            now = self._now()
            state = {
                "owner": owner.namespace_sha256,
                "operation_id": operation_id,
                "envelope_sha256": envelope_hash,
                "created_at": now.isoformat(),
                "expires_at": (now + TTL).isoformat(),
                "status": "inflight",
            }
            # Claim precedes envelope/dispatch. POSIX flushes directory entries too;
            # Windows provides file fsync/atomic replacement, not a portable
            # power-loss directory-durability guarantee.
            self._write(path / "state.json", canonical_bytes(state))
            self._write(claim_path, canonical_bytes({"operation_id": operation_id, "envelope_sha256": envelope_hash}))
            self._write(path / "envelope.json", canonical_bytes(envelope))
            self._write(path / "binding.json", canonical_bytes(dict(binding)))
            self._write(path / "limits.json", canonical_bytes(admitted_limits))
            return ClaimReceipt(operation_id, envelope_hash, "inflight", False, envelope)

    def complete(
        self,
        owner: CallerScope,
        operation_id: str,
        frozen: FrozenPreparation,
        *,
        raw_sources: Mapping[str, bytes] | None = None,
    ) -> None:
        """Freeze content/projections separately; never overwrite a terminal result."""
        frozen = FrozenPreparation.model_validate(frozen)
        packet = PreparationPacket.model_validate_json(frozen.content)
        if packet.envelope.owner != owner or packet.envelope.operation_id != operation_id:
            raise OperationDenied("Packet does not belong to operation")
        bodies = self._raw_packet_bodies(packet, raw_sources)
        with self._lock():
            path, state = self._state(owner, operation_id)
            if state["status"] != "inflight":
                raise OperationConflict("Operation already terminal")
            admitted = self._admitted_envelope(path, state)
            if self._admitted_limits(path) != packet.limits:
                raise OperationConflict("Packet limits differ from admitted policy")
            if admitted != packet.envelope:
                raise OperationConflict("Frozen envelope differs from admitted operation")
            self._validate_packet_corpus(path, packet)
            if freeze_packet(packet) != frozen:
                raise OperationConflict("Projections differ from canonical packet derivation")
            for digest, body in bodies.items():
                self._write(path / (digest + ".source"), body)
            for name, data in [
                ("content.json", frozen.content),
                ("review.md", frozen.review_markdown),
                ("graph.json", frozen.graph),
                ("projections.json", canonical_bytes(frozen.manifest)),
            ]:
                self._write(path / name, data)
            state.update(status=packet.stop_reason, content_sha256=frozen.manifest.content_sha256)
            self._write(path / "state.json", canonical_bytes(state))

    @staticmethod
    def _raw_packet_bodies(packet: PreparationPacket, raw_sources: Mapping[str, bytes] | None) -> dict[str, bytes]:
        """Admit exact retained evidence membership and the packet's byte policy."""
        bodies = dict(raw_sources or {})
        if (
            len(bodies) > packet.limits.sources
            or sum(len(body) for body in bodies.values()) > packet.limits.decoded_bytes
        ):
            raise ValueError("Raw source allowance exceeded")
        for digest, body in bodies.items():
            if (
                _DIGEST.fullmatch(digest) is None
                or sha256(body) != digest
                or len(body) > packet.limits.per_source_bytes
            ):
                raise ValueError("Raw source identity or allowance mismatch")
        expected = {item.raw_sha256 for item in packet.observations if item.raw_sha256 is not None}
        if set(bodies) != expected:
            raise OperationConflict("Retained raw sources differ from packet observations")
        return bodies

    def fail(self, owner: CallerScope, operation_id: str, status: str = "failed") -> None:
        if status not in {"failed", "cancelled", "ambiguous"}:
            raise ValueError("Invalid failure status")
        with self._lock():
            path, state = self._state(owner, operation_id)
            if state["status"] != "inflight":
                raise OperationConflict("Operation already terminal")
            state["status"] = status
            self._write(path / "state.json", canonical_bytes(state))

    def _admitted_limits(self, path: Path) -> PreparationLimits:
        self._check(path / "limits.json", directory=False)
        return PreparationLimits.model_validate_json((path / "limits.json").read_bytes())

    def _admitted_envelope(self, path: Path, state: dict[str, Any]) -> PreparationEnvelope:
        self._check(path / "envelope.json", directory=False)
        envelope = PreparationEnvelope.model_validate_json((path / "envelope.json").read_bytes())
        binding = self._read_json(path / "binding.json")
        if not binding or any(not isinstance(value, str) for value in binding.values()):
            raise StoreProtectionError("Invalid retained service binding")
        bound = envelope.model_dump(mode="json")
        del bound["operation_id"]
        identity = sha256(
            canonical_bytes(
                {"envelope": bound, "binding": binding, "limits": self._admitted_limits(path).model_dump(mode="json")}
            )
        )
        claim_path = path.parent / ("claim_" + sha256(envelope.request.request_id.encode()) + ".json")
        claimed = self._read_json(claim_path)
        if (
            envelope.operation_id != state["operation_id"]
            or envelope.owner.namespace_sha256 != state["owner"]
            or identity != state["envelope_sha256"]
            or claimed.get("envelope_sha256") != identity
            or claimed.get("operation_id") != envelope.operation_id
        ):
            raise StoreProtectionError("Retained admission binding mismatch")
        return envelope

    def load(self, owner: CallerScope, operation_id: str) -> FrozenPreparation:
        with self._lock():
            return self._load_frozen(owner, operation_id)

    def _load_frozen(self, owner: CallerScope, operation_id: str) -> FrozenPreparation:
        path, state = self._state(owner, operation_id)
        if "content_sha256" not in state:
            raise OperationNotReady("No frozen packet")
        admitted = self._admitted_envelope(path, state)
        data = {}
        for field, name in [("content", "content.json"), ("review_markdown", "review.md"), ("graph", "graph.json")]:
            self._check(path / name, directory=False)
            data[field] = (path / name).read_bytes()
        manifest = ProjectionManifest.model_validate(self._read_json(path / "projections.json"))
        if manifest.content_sha256 != state["content_sha256"]:
            raise StoreProtectionError("Frozen content binding mismatch")
        frozen = FrozenPreparation(**data, manifest=manifest)
        packet = PreparationPacket.model_validate_json(frozen.content)
        if (
            packet.envelope != admitted
            or packet.envelope.owner != owner
            or packet.envelope.operation_id != operation_id
            or packet.limits != self._admitted_limits(path)
        ):
            raise StoreProtectionError("Frozen packet admission mismatch")
        if freeze_packet(packet) != frozen:
            raise StoreProtectionError("Frozen projections differ from canonical derivation")
        self._validate_retained_evidence(path, packet, state)
        return frozen

    def _validate_retained_evidence(self, path: Path, packet: PreparationPacket, state: dict[str, Any]) -> None:
        """Validate captured input, raw bodies and normalized corpus as distinct evidence."""
        if state.get("capture_sha256"):
            capture = path / "capture.json"
            self._check(capture, directory=False)
            if capture.stat().st_size > 32 * 1024 * 1024 or sha256(capture.read_bytes()) != state["capture_sha256"]:
                raise StoreProtectionError("Retained capture identity mismatch")
        self._validate_packet_corpus(path, packet)
        expected = {item.raw_sha256 for item in packet.observations if item.raw_sha256 is not None}
        present = {entry.name[:-7] for entry in path.iterdir() if entry.name.endswith(".source")}
        if present != expected:
            raise StoreProtectionError("Frozen raw source inventory mismatch")
        for digest in expected:
            source = path / (digest + ".source")
            self._check(source, directory=False)
            if sha256(source.read_bytes()) != digest:
                raise StoreProtectionError("Frozen raw source hash mismatch")

    def read_source(self, owner: CallerScope, operation_id: str, digest: str) -> bytes:
        if _DIGEST.fullmatch(digest) is None:
            raise OperationDenied("Source unavailable")
        with self._lock():
            frozen = self._load_frozen(owner, operation_id)
            packet = PreparationPacket.model_validate_json(frozen.content)
            if digest not in {item.raw_sha256 for item in packet.observations}:
                raise OperationDenied("Source not admitted in packet")
            path = self._operation(owner, operation_id)
            source = path / (digest + ".source")
            self._check(source, directory=False)
            body = source.read_bytes()
            if sha256(body) != digest:
                raise StoreProtectionError("Raw source identity mismatch")
            return body

    def cleanup(self, *, max_operations: int = 8) -> list[dict[str, Any]]:
        """Rotate a bounded scan; TTL denies access independently of reclamation."""
        if type(max_operations) is not int or not 1 <= max_operations <= 32:
            raise ValueError("Cleanup bound must be 1..32")
        receipts: list[dict[str, Any]] = []
        with self._lock():
            owners = sorted(entry.name for entry in self._inventory(self.root) if _DIGEST.fullmatch(entry.name))
            if len(owners) > _MAX_INVENTORY:
                raise StoreProtectionError("Private root inspection capacity exhausted")
            if not owners:
                return receipts
            cursor = self._read_json(self.root / "cleanup-cursor.json")
            if any(type(cursor.get(key)) is not int or cursor[key] < 0 for key in ("owner", "entry")):
                raise StoreProtectionError("Invalid cleanup cursor")
            owner_index = cursor["owner"] % len(owners)
            entry_index = cursor["entry"]
            scanned = 0
            examined = 0
            while scanned < max_operations * 8 and examined < max_operations:
                owner = CallerScope(namespace_sha256=owners[owner_index])
                namespace = self._owner(owner)
                entries = sorted(self._inventory(namespace), key=lambda entry: entry.name)
                if entry_index >= len(entries):
                    owner_index = (owner_index + 1) % len(owners)
                    entry_index = 0
                    scanned += 1
                    continue
                path = entries[entry_index]
                entry_index += 1
                scanned += 1
                # Persist forward progress even when a later operation fails.
                self._write(
                    self.root / "cleanup-cursor.json", canonical_bytes({"owner": owner_index, "entry": entry_index})
                )
                if not _OPERATION.fullmatch(path.name):
                    continue
                examined += 1
                path, state = self._state(owner, path.name, allow_expired=True)
                if state.get("cleanup_deleted") or self._now() < datetime.fromisoformat(state["expires_at"]):
                    continue
                receipts.append(self._cleanup_operation(path, state))
            self._write(
                self.root / "cleanup-cursor.json", canonical_bytes({"owner": owner_index, "entry": entry_index})
            )
        return receipts

    def _cleanup_operation(self, path: Path, state: dict[str, Any]) -> dict[str, Any]:
        receipt = {key: state[key] for key in ["owner", "operation_id", "envelope_sha256", "expires_at"]}
        receipt.update(
            prior_status=state["status"],
            content_sha256=state.get("content_sha256"),
            cleanup_at=self._now().isoformat(),
            status="cleanup_pending",
            deleted=False,
        )
        self._journal(receipt)
        try:
            for child in path.iterdir():
                if child.name == "state.json":
                    continue
                if child.name == "corpus":
                    self._remove_operation_corpus(child)
                else:
                    self._check(child, directory=False)
                    child.unlink()
            receipt.update(status="deleted", deleted=True)
        except (OSError, StoreProtectionError):
            receipt.update(status="cleanup_failed", deleted=False)
        self._journal(receipt)
        state["cleanup_deleted"] = receipt["deleted"]
        self._write(path / "state.json", canonical_bytes(state))
        return receipt

    def _private_event(self, path: Path, event: dict[str, Any]) -> None:
        """One private append-only journal, always below the same owner/TTL root."""
        for name in ("events.jsonl", "events.jsonl.append.lock"):
            self._prepare_lock(path / name)
        append_jsonl_durable(
            path / "events.jsonl",
            event,
            lock_mode=0o666 if os.name == "nt" else 0o600,
            prepare_lock=self.protection.prepare_empty_lock,
        )
        self._check(path / "events.jsonl", directory=False)

    def retain_capture(self, owner: CallerScope, operation_id: str, content: bytes) -> str:
        if len(content) > 32 * 1024 * 1024:
            raise ValueError("Private captured context exceeds 32MiB serialized bound")
        payload = json.loads(content)
        if canonical_bytes(payload) != content:
            raise ValueError("Captured context must be canonical JSON")
        context = base64.b64decode(payload["context_base64"], validate=True)
        inventory = {}
        total = 0
        for entry in payload["inputs"]:
            raw = base64.b64decode(entry["content_base64"], validate=True)
            total += len(raw)
            if entry["label"] in inventory or sha256(raw) != entry["sha256"]:
                raise ValueError("Captured input identity mismatch")
            inventory[entry["label"]] = entry["sha256"]
        if total > 16 * 1024 * 1024 or sha256(context) != payload["context_sha256"]:
            raise ValueError("Captured input byte bound or context identity mismatch")
        if sha256(canonical_bytes(inventory)) != payload["expert_revision"]:
            raise ValueError("Captured revision identity mismatch")
        with self._lock():
            path, state = self._state(owner, operation_id)
            envelope = self._admitted_envelope(path, state)
            binding = self._read_json(path / "binding.json")
            if state.get("capture_sha256") or payload["expert_revision"] != envelope.expert_revision:
                raise OperationConflict("Captured revision cannot replace admitted input")
            if (
                payload["context_sha256"] != binding.get("captured_context_sha256")
                or payload["question"] != envelope.question
            ):
                raise OperationConflict("Captured context/request identity mismatch")
            self._write(path / "capture.json", content)
            identity = sha256(content)
            state["capture_sha256"] = identity
            self._write(path / "state.json", canonical_bytes(state))
            return identity

    def bind_trace(self, owner: CallerScope, operation_id: str, trace_id: str) -> None:
        if re.fullmatch(r"[A-Za-z0-9_-]{1,128}", trace_id) is None:
            raise ValueError("Invalid internal trace identity")
        with self._lock():
            path, state = self._state(owner, operation_id)
            if "trace_id" in state:
                raise OperationConflict("Operation trace already bound")
            state["trace_id"] = trace_id
            self._write(path / "state.json", canonical_bytes(state))
            self._private_event(path, {"kind": "operation_trace", "trace_id": trace_id})

    def reserve_model_call(
        self,
        owner: CallerScope,
        operation_id: str,
        *,
        phase: str,
        prompt: str,
        model_digest: str,
        options: Mapping[str, Any],
    ) -> int:
        if phase not in {"assumptions", "interpretation"} or not _DIGEST.fullmatch(model_digest):
            raise ValueError("Invalid preparation model identity")
        with self._lock():
            path, state = self._state(owner, operation_id)
            limits = self._admitted_limits(path)
            count = int(state.get("model_calls", 0))
            if (
                state["status"] != "inflight"
                or state.get("model_halted")
                or state.get("acquisition_ambiguous")
                or count >= limits.model_calls
            ):
                raise OperationConflict("Preparation model allowance unavailable")
            if state.get("model_outstanding") or len(prompt) > limits.model_input_chars:
                raise OperationConflict("Preparation model input or outstanding-call refusal")
            count += 1
            state.update(model_calls=count, model_outstanding=count)
            self._write(path / "state.json", canonical_bytes(state))
            self._private_event(
                path,
                {
                    "kind": "model_intent",
                    "call": count,
                    "phase": phase,
                    "prompt": prompt,
                    "prompt_sha256": sha256(prompt.encode()),
                    "prompt_characters": len(prompt),
                    "prompt_utf8_bytes": len(prompt.encode("utf-8")),
                    "model_digest": model_digest,
                    "options": dict(options),
                    "at": self._now().isoformat(),
                },
            )
            return count

    def settle_model_call(
        self,
        owner: CallerScope,
        operation_id: str,
        *,
        call: int,
        raw_response: dict[str, Any] | None,
        status: str,
        error_type: str = "",
    ) -> None:
        if status not in {"returned", "failed", "cancelled", "unknown", "refused_length", "malformed"}:
            raise ValueError("Invalid preparation model outcome")
        with self._lock():
            path, state = self._state(owner, operation_id)
            if state.get("model_outstanding") != call:
                raise OperationConflict("Model settlement does not match outstanding call")
            self._private_event(
                path,
                {
                    "kind": "model_terminal",
                    "call": call,
                    "status": status,
                    "raw_response": raw_response,
                    "error_type": error_type,
                    "usage_known": raw_response is not None and status != "unknown",
                    "at": self._now().isoformat(),
                },
            )
            state.update(model_outstanding=None, model_halted=status != "returned")
            self._write(path / "state.json", canonical_bytes(state))

    def reserve_source(
        self, owner: CallerScope, operation_id: str, *, sequence: int, coordinate_id: str, source_class: str
    ) -> None:
        if source_class not in {"pypi_release", "pypi_index"}:
            raise ValueError("Invalid preparation source class")
        with self._lock():
            path, state = self._state(owner, operation_id)
            envelope = self._admitted_envelope(path, state)
            admitted = {item.coordinate_id for item in envelope.request.packages}
            seen = state.get("source_keys", [])
            key = coordinate_id + ":" + source_class
            if coordinate_id not in admitted or key in seen or sequence != len(seen) + 1:
                raise OperationConflict("Source intent identity refused")
            if (
                state["status"] != "inflight"
                or state.get("model_halted")
                or state.get("acquisition_settled")
                or sequence > self._admitted_limits(path).requests
            ):
                raise OperationConflict("Source allowance unavailable")
            state["source_keys"] = [*seen, key]
            self._write(path / "state.json", canonical_bytes(state))
            self._private_event(
                path,
                {
                    "kind": "source_intent",
                    "sequence": sequence,
                    "coordinate_id": coordinate_id,
                    "source_class": source_class,
                    "at": self._now().isoformat(),
                },
            )

    def record_source_result(
        self,
        owner: CallerScope,
        operation_id: str,
        *,
        sequence: int,
        headers: bytes,
        raw_sha256: str | None,
        outcome: str,
    ) -> None:
        if len(headers) > 8192:
            raise ValueError("Retained header projection exceeds allowance")
        with self._lock():
            path, state = self._state(owner, operation_id)
            if (
                state["status"] != "inflight"
                or sequence in state.get("source_terminals", [])
                or not 1 <= sequence <= len(state.get("source_keys", []))
            ):
                raise OperationConflict("Source result has no durable intent")
            self._private_event(
                path,
                {
                    "kind": "source_terminal",
                    "sequence": sequence,
                    "headers": headers.decode("utf-8"),
                    "raw_sha256": raw_sha256,
                    "outcome": outcome,
                    "at": self._now().isoformat(),
                },
            )
            state["source_terminals"] = [*state.get("source_terminals", []), sequence]
            self._write(path / "state.json", canonical_bytes(state))

    def source_attempt_count(self, owner: CallerScope, operation_id: str) -> int:
        with self._lock():
            _, state = self._state(owner, operation_id)
            return len(state.get("source_keys", []))

    def settle_acquisition(
        self,
        owner: CallerScope,
        operation_id: str,
        *,
        attempts: int,
        decoded_bytes: int,
        stop_reason: str,
        termination_confirmed: bool,
        unreported_read_allowance: int,
        outstanding_intent: dict[str, Any] | None,
    ) -> None:
        with self._lock():
            path, state = self._state(owner, operation_id)
            if state.get("acquisition_settled"):
                raise OperationConflict("Acquisition already settled")
            self._private_event(
                path,
                {
                    "kind": "acquisition_terminal",
                    "attempts": attempts,
                    "decoded_bytes": decoded_bytes,
                    "stop_reason": stop_reason,
                    "termination_confirmed": termination_confirmed,
                    "unreported_read_allowance": unreported_read_allowance,
                    "outstanding_intent": outstanding_intent,
                    "at": self._now().isoformat(),
                },
            )
            state["acquisition_settled"] = True
            state["acquisition_ambiguous"] = (
                not termination_confirmed or bool(unreported_read_allowance) or outstanding_intent is not None
            )
            self._write(path / "state.json", canonical_bytes(state))

    def retain_raw_source(self, owner: CallerScope, operation_id: str, *, digest: str, body: bytes) -> None:
        if _DIGEST.fullmatch(digest) is None or sha256(body) != digest:
            raise ValueError("Raw source identity mismatch")
        with self._lock():
            path, state = self._state(owner, operation_id)
            limits = self._admitted_limits(path)
            retained = state.get("raw_sizes", {})
            if state["status"] != "inflight" or len(body) > limits.per_source_bytes:
                raise OperationConflict("Raw source retention allowance unavailable")
            if digest not in retained and (
                len(retained) >= limits.sources or sum(retained.values()) + len(body) > limits.decoded_bytes
            ):
                raise OperationConflict("Raw source retention allowance exhausted")
            self._write(path / (digest + ".source"), body)
            retained[digest] = len(body)
            state["raw_sizes"] = retained
            self._write(path / "state.json", canonical_bytes(state))

    def retain_corpus_source(
        self,
        owner: CallerScope,
        operation_id: str,
        *,
        text: str,
        coordinate_id: str,
        source_class: str,
        observed_at: str,
    ) -> str:
        """Preprotect the fixed CorpusStore subtree before existing corpus writes."""
        with self._lock():
            path, state = self._state(owner, operation_id)
            envelope = self._admitted_envelope(path, state)
            if coordinate_id not in {item.coordinate_id for item in envelope.request.packages}:
                raise OperationConflict("Corpus coordinate not admitted")
            if source_class not in {"pypi_release", "pypi_index"} or state["status"] != "inflight":
                raise OperationConflict("Corpus source admission refused")
            encoded = text.encode("utf-8")
            if len(encoded) > self._admitted_limits(path).per_source_bytes:
                raise ValueError("Corpus source exceeds byte allowance")
            digest = content_hash(text)
            corpus = path / "corpus"
            for directory in (corpus, corpus / "sources"):
                if not directory.exists():
                    self.protection.protect_new_directory(directory)
                self._check(directory, directory=True)
            entries = self._corpus_files(corpus)
            limits = self._admitted_limits(path)
            is_new = not (corpus / "sources" / digest[:2] / (digest + ".md")).exists()
            sources = [entry for entry in entries if entry.suffix == ".md"]
            if is_new and (
                len(sources) >= limits.sources
                or sum(entry.stat().st_size for entry in sources) + len(encoded) > limits.decoded_bytes
            ):
                raise OperationConflict("Operation corpus cumulative allowance exhausted")
            fanout = corpus / "sources" / digest[:2]
            if not fanout.exists():
                if len(self._inventory(corpus / "sources")) >= limits.sources:
                    raise OperationConflict("Operation corpus fanout allowance exhausted")
                self.protection.protect_new_directory(fanout)
            self._check(fanout, directory=True)
            if not (corpus / "sources" / digest[:2] / (digest + ".md")).exists() and len(entries) >= 7:
                raise OperationConflict("Operation corpus source allowance exhausted")
            temporary = CorpusStore(
                "temporary-preparation", storage_dir=corpus, prepare_tempfile=self.protection.prepare_tempfile
            )
            entry, _ = temporary.add(
                text,
                origin_key=f"{source_class}:{coordinate_id}",
                title=coordinate_id,
                kind="preparation_metadata",
                fetched_at=observed_at,
            )
            self._corpus_files(corpus)
            return entry.sha256

    def _corpus_files(self, corpus: Path) -> list[Path]:
        self._check(corpus, directory=True)
        files = []
        for entry in self._inventory(corpus):
            if entry.name == "index.jsonl":
                self._check(entry, directory=False)
                files.append(entry)
                continue
            if entry.name != "sources":
                raise StoreProtectionError("Unexpected operation corpus entry")
            self._check(entry, directory=True)
            prefixes = self._inventory(entry)
            if len(prefixes) > 6:
                raise StoreProtectionError("Operation corpus fanout exceeds allowance")
            for prefix in prefixes:
                if re.fullmatch(r"[0-9a-f]{2}", prefix.name) is None:
                    raise StoreProtectionError("Unexpected corpus fanout")
                self._check(prefix, directory=True)
                for source in self._inventory(prefix):
                    if re.fullmatch(prefix.name + r"[0-9a-f]{62}\.md", source.name) is None:
                        raise StoreProtectionError("Unexpected operation corpus source")
                    self._check(source, directory=False)
                    files.append(source)
        if len(files) > 7:
            raise StoreProtectionError("Operation corpus inventory exceeds allowance")
        return files

    def _validate_packet_corpus(self, path: Path, packet: PreparationPacket) -> None:
        expected = {item.corpus_sha256 for item in packet.observations if item.corpus_sha256 is not None}
        corpus = path / "corpus"
        if not corpus.exists():
            if expected:
                raise OperationConflict("Referenced operation corpus unavailable")
            return
        files = self._corpus_files(corpus)
        present = {entry.stem for entry in files if entry.suffix == ".md"}
        if present != expected:
            raise OperationConflict("Operation corpus does not match frozen observations")
        for entry in files:
            if entry.suffix == ".md" and content_hash(entry.read_text(encoding="utf-8")) != entry.stem:
                raise StoreProtectionError("Operation corpus content hash mismatch")
        retained = CorpusStore("temporary-preparation", storage_dir=corpus)
        if set(retained.entries) != expected:
            raise StoreProtectionError("Operation corpus index identity mismatch")

    def _remove_operation_corpus(self, corpus: Path) -> None:
        for source in self._corpus_files(corpus):
            source.unlink()
        sources = corpus / "sources"
        if sources.exists():
            for prefix in self._inventory(sources):
                self._check(prefix, directory=True)
                prefix.rmdir()
            sources.rmdir()
        corpus.rmdir()

    def record_delivery(
        self,
        owner: CallerScope,
        operation_id: str,
        *,
        packet_sha256: str,
        messages: bytes | None,
        answer: bytes | None = None,
        status: str = "dispatch_intent",
    ) -> None:
        """Append exact later delivery, or hash-only refusal when body is too large."""
        if status not in {
            "dispatch_intent",
            "completed",
            "failed",
            "truncated",
            "cancelled_or_failed",
            "not_delivered",
        }:
            raise ValueError("Invalid delivery receipt status")
        available = (messages is None or len(messages) <= 131072) and (answer is None or len(answer) <= 131072)
        if (messages is None) != (status == "not_delivered"):
            raise ValueError("Missing message body requires not-delivered disposition")
        with self._lock():
            frozen = self._load_frozen(owner, operation_id)
            if frozen.manifest.content_sha256 != packet_sha256:
                raise OperationConflict("Delivery packet identity differs")
            path, state = self._state(owner, operation_id)
            count = int(state.get("delivery_records", 0))
            if (
                count >= 2
                or state.get("delivery_terminal")
                or (count == 0 and status not in {"dispatch_intent", "not_delivered"})
                or (count == 1 and status == "dispatch_intent")
            ):
                raise OperationConflict("Delivery receipt phase or allowance refused")
            self._private_event(
                path,
                {
                    "kind": "delivery",
                    "status": status,
                    "packet_sha256": packet_sha256,
                    "messages": messages.decode("utf-8") if messages is not None and available else None,
                    "messages_sha256": sha256(messages) if messages is not None else None,
                    "answer": answer.decode("utf-8") if answer is not None and available else None,
                    "answer_sha256": sha256(answer) if answer is not None else None,
                    "body_available": available,
                    "at": self._now().isoformat(),
                },
            )
            state["delivery_records"] = count + 1
            state["delivery_terminal"] = status != "dispatch_intent" or not available
            self._write(path / "state.json", canonical_bytes(state))
            if not available:
                raise OperationConflict("Private delivery body unavailable: artifact bound exceeded; hashes retained")

    def _journal(self, record: dict[str, Any]) -> None:
        self._prepare_lock(self.root / "tombstones.jsonl.append.lock")
        for name in ["tombstones.jsonl", "tombstones.jsonl.append.lock"]:
            self._check(self.root / name, directory=False)
        append_jsonl_durable(
            self.root / "tombstones.jsonl",
            record,
            lock_mode=0o666 if os.name == "nt" else 0o600,
            prepare_lock=self.protection.prepare_empty_lock,
        )
        self._check(self.root / "tombstones.jsonl", directory=False)
