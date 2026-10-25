"""Private offline preparation operations, not caller authentication or a sandbox.

Callers supply an explicit root and a trusted service-derived CallerScope. No
public interface, inference, acquisition or canonical expert state is touched.
Windows uses the existing optional pywin32 dependency lazily and fails closed
without it. Clean core-install Windows support is unqualified; docs/full brings
pywin32 transitively through docx2pdf. This module adds no dependency.
"""

from __future__ import annotations

import json
import os
import re
import stat
import sys
import uuid
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import islice
from pathlib import Path
from typing import Any

from filelock import FileLock

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
from deepr.utils.atomic_io import append_jsonl_durable, atomic_write_bytes

TTL = timedelta(days=7)
# Offline prototype inspection ceilings, not source/semantic selection rules.
_MAX_INVENTORY = 256
_MARKER = b"deepr-private-preparation-store-v1\n"
_OPERATION = re.compile(r"^op_[0-9a-f]{32}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


class PreparationStoreError(RuntimeError):
    """A store operation failed without granting new execution authority."""


class StoreProtectionError(PreparationStoreError):
    """Private storage protection could not be established or verified."""


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


class _Protection:
    """Current-token/UID protection; never repairs unrelated existing storage."""

    def __init__(self) -> None:
        self.sid: Any = None
        self.security: Any = None
        if os.name == "nt":
            try:
                import pywintypes
                import win32api
                import win32con
                import win32security

                self.security = win32security
                try:
                    token = win32security.OpenThreadToken(win32api.GetCurrentThread(), win32con.TOKEN_QUERY, True)
                except pywintypes.error as error:
                    if error.winerror != 1008:
                        raise
                    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
                try:
                    self.sid = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
                finally:
                    token.Close()
            except Exception as error:
                raise StoreProtectionError("Current Windows token identity unavailable") from error

    def protect_new_directory(self, path: Path) -> None:
        path.mkdir(mode=0o700)
        if os.name == "nt":
            security = self.security
            system = security.CreateWellKnownSid(security.WinLocalSystemSid)
            acl = security.ACL()
            for sid in (self.sid, system):
                acl.AddAccessAllowedAceEx(security.ACL_REVISION, 3, 0x1F01FF, sid)
            security.SetNamedSecurityInfo(
                str(path),
                security.SE_FILE_OBJECT,
                security.OWNER_SECURITY_INFORMATION
                | security.DACL_SECURITY_INFORMATION
                | security.PROTECTED_DACL_SECURITY_INFORMATION,
                self.sid,
                None,
                acl,
                None,
            )
        self.verify(path, directory=True, protected=True)

    def prepare_tempfile(self, descriptor: int, path: Path) -> None:
        """Protect the same empty open file before any private payload write."""
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size != 0 or info.st_nlink != 1:
            raise StoreProtectionError("Expected a new empty private file")
        if sys.platform == "win32":
            import msvcrt

            self._set_empty_windows_owner(path, expected_handle=msvcrt.get_osfhandle(descriptor))
        self.verify(path, directory=False)

    def prepare_empty_lock(self, path: Path) -> None:
        """Correct only a known empty lock's creation owner, never its DACL."""
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size != 0 or info.st_nlink != 1:
            raise StoreProtectionError("Expected an empty private lock")
        if sys.platform == "win32":
            self._set_empty_windows_owner(path)
        self.verify(path, directory=False)

    def _set_empty_windows_owner(self, path: Path, *, expected_handle: int | None = None) -> None:
        """TokenOwner may differ from TokenUser on an elevated Windows runner."""
        import ntsecuritycon
        import win32con
        import win32file

        handle = win32file.CreateFile(
            str(path),
            win32con.WRITE_OWNER | win32con.READ_CONTROL | ntsecuritycon.FILE_READ_ATTRIBUTES,
            win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE | win32con.FILE_SHARE_DELETE,
            None,
            win32con.OPEN_EXISTING,
            win32file.FILE_FLAG_OPEN_REPARSE_POINT,
            None,
        )
        try:
            info = win32file.GetFileInformationByHandle(handle)
            if info[0] & 0x400 or info[5] != 0 or info[6] != 0 or info[7] != 1:
                raise StoreProtectionError("Unexpected empty Windows file identity")
            if expected_handle is not None:
                original = win32file.GetFileInformationByHandle(expected_handle)
                if (info[4], info[8], info[9]) != (original[4], original[8], original[9]):
                    raise StoreProtectionError("Windows tempfile handle identity changed")
            self.security.SetSecurityInfo(
                handle,
                self.security.SE_FILE_OBJECT,
                self.security.OWNER_SECURITY_INFORMATION,
                self.sid,
                None,
                None,
                None,
            )
            descriptor = self.security.GetSecurityInfo(
                handle, self.security.SE_FILE_OBJECT, self.security.OWNER_SECURITY_INFORMATION
            )
            if descriptor.GetSecurityDescriptorOwner() != self.sid:
                raise StoreProtectionError("Windows private owner assignment failed")
        finally:
            handle.Close()

    def verify(self, path: Path, *, directory: bool, protected: bool = False) -> None:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise StoreProtectionError("Links and reparse points are refused")
        if directory != stat.S_ISDIR(info.st_mode) or (not directory and info.st_nlink != 1):
            raise StoreProtectionError("Unexpected private storage entry")
        if sys.platform != "win32":
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600):
                raise StoreProtectionError("Private storage must be current-UID owner only")
            return
        self._verify_windows_acl(path, directory=directory, protected=protected)

    def _verify_windows_acl(self, path: Path, *, directory: bool, protected: bool) -> None:
        """Verify owner, exact principals and child-propagation protection."""
        security = self.security
        descriptor = security.GetNamedSecurityInfo(
            str(path),
            security.SE_FILE_OBJECT,
            security.OWNER_SECURITY_INFORMATION | security.DACL_SECURITY_INFORMATION,
        )
        if descriptor.GetSecurityDescriptorOwner() != self.sid:
            raise StoreProtectionError("Unexpected Windows owner")
        control, _ = descriptor.GetSecurityDescriptorControl()
        if protected and not control & 0x1000:
            raise StoreProtectionError("Windows DACL inheritance must be protected")
        acl = descriptor.GetSecurityDescriptorDacl()
        if acl is None or acl.GetAceCount() != 2:
            raise StoreProtectionError("Unexpected Windows private DACL")
        allowed = {str(self.sid), str(security.CreateWellKnownSid(security.WinLocalSystemSid))}
        observed = set()
        for index in range(acl.GetAceCount()):
            header, mask, sid = acl.GetAce(index)
            if header[0] != security.ACCESS_ALLOWED_ACE_TYPE or mask != 0x1F01FF or str(sid) not in allowed:
                raise StoreProtectionError("Unexpected Windows private ACE")
            inheritance = header[1] & 0x0F
            if inheritance != (3 if directory else 0):
                raise StoreProtectionError("Unexpected Windows ACE inheritance flags")
            observed.add(str(sid))
        if observed != allowed:
            raise StoreProtectionError("Missing private Windows principal")


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
            if index >= 16:
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
        expected = {item.raw_sha256 for item in packet.observations if item.raw_sha256 is not None}
        present = {entry.name[:-7] for entry in path.iterdir() if entry.name.endswith(".source")}
        if present != expected:
            raise StoreProtectionError("Frozen raw source inventory mismatch")
        for digest in expected:
            source = path / (digest + ".source")
            self._check(source, directory=False)
            if sha256(source.read_bytes()) != digest:
                raise StoreProtectionError("Frozen raw source hash mismatch")
        return frozen

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
                self._check(child, directory=False)
                child.unlink()
            receipt.update(status="deleted", deleted=True)
        except (OSError, StoreProtectionError):
            receipt.update(status="cleanup_failed", deleted=False)
        self._journal(receipt)
        state["cleanup_deleted"] = receipt["deleted"]
        self._write(path / "state.json", canonical_bytes(state))
        return receipt

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
