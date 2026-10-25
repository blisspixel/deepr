"""Synthetic private-store fixtures, with real platform permission admission."""

import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from deepr.experts.preparation_contracts import (
    CallerScope,
    FrozenPreparation,
    PackageCoordinate,
    PreparationLimits,
    PreparationPacket,
    PreparationRequest,
    ProjectionManifest,
    PythonEnvironment,
    SourceObservation,
    freeze_packet,
    sha256,
)
from deepr.experts.preparation_store import (
    OperationConflict,
    OperationDenied,
    OperationExpired,
    OperationNotReady,
    PreparationStore,
    StoreProtectionError,
)


@pytest.fixture
def setup_store(tmp_path):
    now = [datetime(2026, 10, 25, tzinfo=UTC)]
    store = PreparationStore(tmp_path / "private", clock=lambda: now[0])
    owner = CallerScope(namespace_sha256="a" * 64)
    request = PreparationRequest(
        schema_version="deepr-python-preparation-request-v1",
        enabled=True,
        request_id="synthetic_request_001",
        environment=PythonEnvironment(interpreter_version="3.12", platform="synthetic"),
        packages=(PackageCoordinate(name="example", version="1.0"),),
    )
    return store, owner, request, now


def claim(store, owner, request, question="Synthetic question?"):
    return store.claim(owner, request, question, "b" * 64, binding={"policy": "fixture", "model": "offline"})


def test_claim_once_terminal_duplicate_has_no_payload_or_allowance(setup_store):
    store, owner, request, _ = setup_store
    first = claim(store, owner, request)
    duplicate = claim(store, owner, request)
    assert duplicate.duplicate and duplicate.operation_id == first.operation_id
    assert duplicate.envelope is None
    assert duplicate.status == "inflight"
    frozen = freeze_packet(PreparationPacket(envelope=first.envelope, stop_reason="offline"))
    store.complete(owner, first.operation_id, frozen)
    assert store.load(owner, first.operation_id) == frozen
    completed = claim(store, owner, request)
    assert completed.duplicate and completed.status == "offline" and completed.envelope is None
    with pytest.raises(OperationConflict):
        store.complete(owner, first.operation_id, frozen)


def test_changed_envelope_or_policy_conflicts(setup_store):
    store, owner, request, _ = setup_store
    claim(store, owner, request)
    with pytest.raises(OperationConflict):
        claim(store, owner, request, "Changed private question")
    with pytest.raises(OperationConflict):
        store.claim(owner, request, "Synthetic question?", "b" * 64, binding={"policy": "changed"})


def test_namespace_is_owner_bound_not_question_sharing(setup_store):
    store, owner, request, _ = setup_store
    first = claim(store, owner, request)
    other = CallerScope(namespace_sha256="c" * 64)
    with pytest.raises(OperationDenied):
        store.load(other, first.operation_id)
    second = claim(store, other, request)
    assert second.operation_id != first.operation_id
    with pytest.raises(OperationNotReady):
        store.load(owner, first.operation_id)


@pytest.mark.parametrize("operation_id", ["../escape", "/absolute", "op_bad", "..\\escape"])
def test_traversal_is_typed_denied(setup_store, operation_id):
    store, owner, _, _ = setup_store
    with pytest.raises(OperationDenied):
        store.load(owner, operation_id)


def test_raw_sources_separate_hashes_and_all_read_paths_expire(setup_store):
    store, owner, request, now = setup_store
    first = claim(store, owner, request)
    body = b"synthetic retained source"
    digest = sha256(body)
    observation = SourceObservation(
        observation_id="source_1",
        coordinate_id=request.packages[0].coordinate_id,
        source_class="pypi_release",
        requested_at=now[0],
        observed_at=now[0],
        status="partial",
        raw_sha256=digest,
    )
    frozen = freeze_packet(
        PreparationPacket(envelope=first.envelope, observations=(observation,), stop_reason="partial")
    )
    store.complete(owner, first.operation_id, frozen, raw_sources={digest: body})
    assert store.read_source(owner, first.operation_id, digest) == body
    now[0] += timedelta(days=7)
    for read in [
        lambda: store.load(owner, first.operation_id),
        lambda: store.read_source(owner, first.operation_id, digest),
    ]:
        with pytest.raises(OperationExpired):
            read()
    assert claim(store, owner, request).status == "expired"
    receipts = store.cleanup()
    assert receipts[0]["deleted"]
    assert not list(store.root.rglob("*.source"))
    journal = (store.root / "tombstones.jsonl").read_text()
    assert "Synthetic question" not in journal and "synthetic retained" not in journal
    assert json.loads(journal.splitlines()[-1])["deleted"] is True
    assert claim(store, owner, request).duplicate


def test_cleanup_failure_never_reports_deletion_or_restores_access(setup_store, monkeypatch):
    store, owner, request, now = setup_store
    first = claim(store, owner, request)
    now[0] += timedelta(days=8)
    original = Path.unlink

    def denied(path, *args, **kwargs):
        if path.name == "envelope.json":
            raise PermissionError("synthetic deletion failure")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", denied)
    receipts = store.cleanup(max_operations=1)
    assert receipts[0]["status"] == "cleanup_failed" and not receipts[0]["deleted"]
    with pytest.raises(OperationExpired):
        store.load(owner, first.operation_id)


def test_existing_unrelated_root_is_not_repaired(tmp_path):
    root = tmp_path / "unrelated"
    root.mkdir()
    data = root / "keep.txt"
    data.write_text("preserve")
    before = root.stat().st_mode
    with pytest.raises(StoreProtectionError):
        PreparationStore(root)
    assert data.read_text() == "preserve" and root.stat().st_mode == before


def test_real_private_permissions_and_reopen(setup_store):
    store, owner, request, now = setup_store
    first = claim(store, owner, request)
    for path in [store.root, *store.root.rglob("*")]:
        store.protection.verify(path, directory=path.is_dir(), protected=path.is_dir())
        if os.name != "nt":
            assert path.stat().st_mode & 0o777 == (0o700 if path.is_dir() else 0o600)
    reopened = PreparationStore(store.root, clock=lambda: now[0])
    assert claim(reopened, owner, request).operation_id == first.operation_id


def test_source_and_envelope_identity_refused(setup_store):
    store, owner, request, _ = setup_store
    first = claim(store, owner, request)
    frozen = freeze_packet(PreparationPacket(envelope=first.envelope, stop_reason="offline"))
    with pytest.raises(ValueError, match="identity"):
        store.complete(owner, first.operation_id, frozen, raw_sources={"0" * 64: b"changed"})
    wrong = first.envelope.model_copy(update={"question": "changed"})
    with pytest.raises(OperationConflict):
        store.complete(
            owner, first.operation_id, freeze_packet(PreparationPacket(envelope=wrong, stop_reason="offline"))
        )


def test_failed_operation_duplicate_cannot_restart(setup_store):
    store, owner, request, _ = setup_store
    first = claim(store, owner, request)
    store.fail(owner, first.operation_id, "ambiguous")
    assert claim(store, owner, request).status == "ambiguous"
    with pytest.raises(OperationConflict):
        store.fail(owner, first.operation_id)


def test_linked_private_file_is_refused(setup_store, tmp_path):
    store, owner, request, _ = setup_store
    first = claim(store, owner, request)
    source = store.root / owner.namespace_sha256 / first.operation_id / "envelope.json"
    os.link(source, tmp_path / "alias")
    with pytest.raises(StoreProtectionError):
        store.complete(
            owner, first.operation_id, freeze_packet(PreparationPacket(envelope=first.envelope, stop_reason="offline"))
        )


def test_weakened_real_permissions_refuse_access(setup_store):
    store, owner, request, _ = setup_store
    first = claim(store, owner, request)
    if os.name == "nt":
        security = store.protection.security
        descriptor = security.GetNamedSecurityInfo(
            str(store.root), security.SE_FILE_OBJECT, security.DACL_SECURITY_INFORMATION
        )
        acl = descriptor.GetSecurityDescriptorDacl()
        acl.AddAccessAllowedAceEx(
            security.ACL_REVISION, 3, 0x1F01FF, security.CreateWellKnownSid(security.WinBuiltinUsersSid)
        )
        security.SetNamedSecurityInfo(
            str(store.root),
            security.SE_FILE_OBJECT,
            security.DACL_SECURITY_INFORMATION | security.PROTECTED_DACL_SECURITY_INFORMATION,
            None,
            None,
            acl,
            None,
        )
    else:
        store.root.chmod(0o755)
    with pytest.raises(StoreProtectionError):
        store.load(owner, first.operation_id)


def test_unassociated_or_missing_raw_bodies_refused(setup_store):
    store, owner, request, now = setup_store
    first = claim(store, owner, request)
    body = b"synthetic"
    digest = sha256(body)
    empty = freeze_packet(PreparationPacket(envelope=first.envelope, stop_reason="offline"))
    with pytest.raises(OperationConflict, match="raw sources"):
        store.complete(owner, first.operation_id, empty, raw_sources={digest: body})
    observation = SourceObservation(
        observation_id="source_1",
        coordinate_id=request.packages[0].coordinate_id,
        source_class="pypi_release",
        requested_at=now[0],
        observed_at=now[0],
        status="partial",
        raw_sha256=digest,
    )
    observed = freeze_packet(
        PreparationPacket(envelope=first.envelope, observations=(observation,), stop_reason="partial")
    )
    with pytest.raises(OperationConflict, match="raw sources"):
        store.complete(owner, first.operation_id, observed)


def test_self_consistent_arbitrary_projection_is_not_accepted(setup_store):
    store, owner, request, _ = setup_store
    first = claim(store, owner, request)
    frozen = freeze_packet(PreparationPacket(envelope=first.envelope, stop_reason="offline"))
    forged = FrozenPreparation(
        content=frozen.content,
        review_markdown=b"invented",
        graph=frozen.graph,
        manifest=ProjectionManifest(
            content_sha256=sha256(frozen.content),
            review_markdown_sha256=sha256(b"invented"),
            graph_sha256=sha256(frozen.graph),
        ),
    )
    with pytest.raises(OperationConflict, match="Projections"):
        store.complete(owner, first.operation_id, forged)


def test_retained_binding_is_validated_on_completion_and_load(setup_store):
    store, owner, request, _ = setup_store
    first = claim(store, owner, request)
    frozen = freeze_packet(PreparationPacket(envelope=first.envelope, stop_reason="offline"))
    path = store.root / owner.namespace_sha256 / first.operation_id / "binding.json"
    original = path.read_bytes()
    store._write(path, b'{"policy":"changed"}')
    with pytest.raises(StoreProtectionError, match="binding"):
        store.complete(owner, first.operation_id, frozen)
    store._write(path, original)
    store.complete(owner, first.operation_id, frozen)
    store._write(path, b'{"model":"changed"}')
    with pytest.raises(StoreProtectionError, match="binding"):
        store.load(owner, first.operation_id)


def test_failed_observation_without_returned_bytes_needs_no_raw_body(setup_store):
    store, owner, request, now = setup_store
    first = claim(store, owner, request)
    observation = SourceObservation(
        observation_id="failed_1",
        coordinate_id=request.packages[0].coordinate_id,
        source_class="pypi_release",
        requested_at=now[0],
        observed_at=now[0],
        status="failed",
    )
    frozen = freeze_packet(
        PreparationPacket(envelope=first.envelope, observations=(observation,), stop_reason="failed")
    )
    store.complete(owner, first.operation_id, frozen)
    assert store.load(owner, first.operation_id) == frozen
    with pytest.raises(OperationDenied):
        store.read_source(owner, first.operation_id, "e" * 64)


def test_cleanup_cursor_reaches_later_expired_operations(setup_store):
    store, owner, request, now = setup_store
    operations = [
        claim(store, owner, request.model_copy(update={"request_id": f"synthetic_request_{index:03d}"})).operation_id
        for index in range(4)
    ]
    now[0] += timedelta(days=8)
    deleted = set()
    for _ in range(12):
        deleted.update(receipt["operation_id"] for receipt in store.cleanup(max_operations=1) if receipt["deleted"])
        if deleted == set(operations):
            break
    assert deleted == set(operations)


def test_namespace_capacity_refuses_before_insert_and_preserves_reads(setup_store, monkeypatch):
    from deepr.experts import preparation_store

    store, owner, request, _ = setup_store
    first = claim(store, owner, request)
    monkeypatch.setattr(preparation_store, "_MAX_INVENTORY", 6)
    second = request.model_copy(update={"request_id": "second_request_001"})
    claim(store, owner, second)
    third = request.model_copy(update={"request_id": "third_request_001"})
    claim(store, owner, third)
    fourth = request.model_copy(update={"request_id": "fourth_request_001"})
    with pytest.raises(StoreProtectionError, match="capacity"):
        claim(store, owner, fourth)
    assert claim(store, owner, request).operation_id == first.operation_id
    with pytest.raises(OperationNotReady):
        store.load(owner, first.operation_id)
    another = CallerScope(namespace_sha256="d" * 64)
    with pytest.raises(StoreProtectionError, match="capacity"):
        claim(store, another, request)


def test_projection_tamper_with_consistent_hashes_refused_on_load(setup_store):
    store, owner, request, _ = setup_store
    first = claim(store, owner, request)
    frozen = freeze_packet(PreparationPacket(envelope=first.envelope, stop_reason="offline"))
    store.complete(owner, first.operation_id, frozen)
    directory = store.root / owner.namespace_sha256 / first.operation_id
    store._write(directory / "review.md", b"invented")
    manifest = frozen.manifest.model_copy(update={"review_markdown_sha256": sha256(b"invented")})
    from deepr.experts.preparation_contracts import canonical_bytes

    store._write(directory / "projections.json", canonical_bytes(manifest))
    with pytest.raises(StoreProtectionError, match="canonical"):
        store.load(owner, first.operation_id)


def test_parent_protection_refused_before_any_private_child_bytes(setup_store, monkeypatch):
    store, owner, request, _ = setup_store
    if os.name == "nt":
        security = store.protection.security
        descriptor = security.GetNamedSecurityInfo(
            str(store.root), security.SE_FILE_OBJECT, security.DACL_SECURITY_INFORMATION
        )
        old_acl = descriptor.GetSecurityDescriptorDacl()
        acl = security.ACL()
        for index in range(old_acl.GetAceCount()):
            _, mask, sid = old_acl.GetAce(index)
            acl.AddAccessAllowedAceEx(security.ACL_REVISION, 0, mask, sid)
        security.SetNamedSecurityInfo(
            str(store.root),
            security.SE_FILE_OBJECT,
            security.DACL_SECURITY_INFORMATION | security.PROTECTED_DACL_SECURITY_INFORMATION,
            None,
            None,
            acl,
            None,
        )
    else:
        store.root.chmod(0o755)
    with pytest.raises(StoreProtectionError):
        claim(store, owner, request)
    assert not list(store.root.rglob("envelope.json"))


def test_normal_no_thread_token_uses_real_process_token(setup_store, monkeypatch, tmp_path):
    store, _, _, _ = setup_store
    if os.name == "nt":
        import pywintypes
        import win32security

        def no_thread_token(*args):
            raise pywintypes.error(
                1008, "OpenThreadToken", "An attempt was made to reference a token that does not exist."
            )

        monkeypatch.setattr(win32security, "OpenThreadToken", no_thread_token)
        real = PreparationStore(tmp_path / "process-token-private")
        assert real.protection.sid == store.protection.sid
        real.protection.verify(real.root, directory=True, protected=True)
    else:
        assert store.root.stat().st_uid == os.getuid()


def test_lower_limits_are_admitted_and_enforced(setup_store):
    store, owner, request, now = setup_store
    limits = PreparationLimits(per_source_bytes=3, decoded_bytes=4, sources=1)
    first = store.claim(
        owner, request, "bounded", "b" * 64, binding={"policy": "small", "model": "offline"}, limits=limits
    )
    body = b"four"
    observation = SourceObservation(
        observation_id="source",
        coordinate_id=request.packages[0].coordinate_id,
        source_class="pypi_release",
        requested_at=now[0],
        observed_at=now[0],
        status="partial",
        raw_sha256=sha256(body),
    )
    packet = PreparationPacket(
        envelope=first.envelope, observations=(observation,), limits=limits, stop_reason="partial"
    )
    with pytest.raises(ValueError, match="allowance"):
        store.complete(owner, first.operation_id, freeze_packet(packet), raw_sources={sha256(body): body})
    changed = packet.model_copy(update={"limits": PreparationLimits()})
    with pytest.raises(OperationConflict, match="limits"):
        store.complete(owner, first.operation_id, freeze_packet(changed), raw_sources={sha256(body): body})


def test_atomic_tempfile_is_private_before_first_payload_byte(setup_store, monkeypatch):
    store, owner, request, _ = setup_store
    first = claim(store, owner, request)
    original = store.protection.prepare_tempfile
    observed = []

    def checked_tempfile(descriptor, path):
        original(descriptor, path)
        store.protection.verify(path, directory=False)
        assert os.fstat(descriptor).st_size == 0
        observed.append(path)

    monkeypatch.setattr(store.protection, "prepare_tempfile", checked_tempfile)
    frozen = freeze_packet(PreparationPacket(envelope=first.envelope, stop_reason="offline"))
    store.complete(owner, first.operation_id, frozen)
    assert len(observed) >= 5


@pytest.mark.parametrize("same_file", [True, False], ids=["elevated-owner", "changed-file"])
def test_windows_creation_owner_is_corrected_to_actual_token_user_before_bytes(monkeypatch, tmp_path, same_file):
    from deepr.experts.preparation_store import _Protection

    state = {"owner": "Administrators", "closed": False}
    owner_information = 1

    class Handle:
        def Close(self):
            state["closed"] = True

    handle = Handle()
    info = (0, None, None, None, 42, 0, 0, 1, 0, 123)

    def file_info(value):
        if value == 77 and not same_file:
            return (*info[:9], 124)
        return info

    native = SimpleNamespace(
        CreateFile=lambda *args: handle, GetFileInformationByHandle=file_info, FILE_FLAG_OPEN_REPARSE_POINT=0x200000
    )
    constants = SimpleNamespace(
        WRITE_OWNER=0x80000,
        READ_CONTROL=0x20000,
        FILE_READ_ATTRIBUTES=0x80,
        FILE_SHARE_READ=1,
        FILE_SHARE_WRITE=2,
        FILE_SHARE_DELETE=4,
        OPEN_EXISTING=3,
        FILE_FLAG_OPEN_REPARSE_POINT=0x200000,
    )

    def set_owner(actual_handle, object_type, information, owner, group, dacl, sacl):
        assert actual_handle is handle
        assert information == owner_information
        assert group is dacl is sacl is None
        state["owner"] = owner

    protection = object.__new__(_Protection)
    protection.sid = "actual-token-user"
    protection.security = SimpleNamespace(
        SE_FILE_OBJECT=1,
        OWNER_SECURITY_INFORMATION=owner_information,
        SetSecurityInfo=set_owner,
        GetSecurityInfo=lambda *args: SimpleNamespace(GetSecurityDescriptorOwner=lambda: state["owner"]),
    )
    monkeypatch.setitem(sys.modules, "win32con", constants)
    monkeypatch.setitem(sys.modules, "win32file", native)
    monkeypatch.setitem(sys.modules, "ntsecuritycon", SimpleNamespace(FILE_READ_ATTRIBUTES=0x80))
    if same_file:
        protection._set_empty_windows_owner(tmp_path / "empty", expected_handle=77)
        assert state["owner"] == "actual-token-user"
    else:
        with pytest.raises(StoreProtectionError, match="identity changed"):
            protection._set_empty_windows_owner(tmp_path / "empty", expected_handle=77)
        assert state["owner"] == "Administrators"
    assert state["closed"]


def _cross_process_claim(root, request_json, result_queue):
    try:
        store = PreparationStore(Path(root))
        owner = CallerScope(namespace_sha256="a" * 64)
        request = PreparationRequest.model_validate_json(request_json)
        receipt = claim(store, owner, request)
        result_queue.put((receipt.operation_id, receipt.duplicate))
    except Exception as error:
        result_queue.put((type(error).__name__, str(error)))


def test_cross_process_same_key_admits_exactly_once(setup_store):
    import multiprocessing

    store, _, request, _ = setup_store
    context = multiprocessing.get_context("spawn")
    results = context.Queue()
    processes = [
        context.Process(target=_cross_process_claim, args=(str(store.root), request.model_dump_json(), results))
        for _ in range(2)
    ]
    try:
        for process in processes:
            process.start()
        receipts = [results.get(timeout=30) for _ in processes]
        for process in processes:
            process.join(timeout=30)
            assert process.exitcode == 0
        assert len({receipt[0] for receipt in receipts}) == 1
        assert sorted(receipt[1] for receipt in receipts) == [False, True]
    finally:
        for process in processes:
            if process.is_alive():
                process.kill()
                process.join(timeout=10)
        results.close()
