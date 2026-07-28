"""Offline billing reconciliation and fail-closed apply tests."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from deepr.observability import provider_account_controls as account_controls_module
from deepr.observability import provider_billing as billing_module
from deepr.observability.cost_ledger import CostLedger, CostLedgerEvent
from deepr.observability.provider_account_controls import (
    PaidApiAccountEvidence,
    ProviderAccountBinding,
    ProviderAccountControlError,
    ProviderAccountEvidenceStore,
    verify_paid_api_authorization,
)
from deepr.observability.provider_billing import (
    BillingEvidenceStore,
    ProviderBillingStorageError,
    ProviderBillingValidationError,
    load_billing_import,
    locked_ledger_snapshot,
    read_only_ledger_snapshot,
    reconcile_billing,
    reconcile_billing_file,
)

_PRODUCTION_SOURCE_VERIFIER = account_controls_module._verify_authenticated_account_evidence_source
_PRODUCTION_BINDING_RESOLVER = account_controls_module._resolve_current_provider_account_binding


def _line(
    *,
    line_id: str = "line-1",
    charge: str = "1.250000",
    credit: str = "0",
    adjustment: str = "0",
    tax: str = "0",
    net: str = "1.250000",
    request_id: str = "req-1",
) -> dict[str, object]:
    return {
        "line_id": line_id,
        "category": "metered_api",
        "capacity_class": "api_metered",
        "usage_start": "2026-07-01T01:00:00+00:00",
        "usage_end": "2026-07-01T01:01:00+00:00",
        "charge_usd": charge,
        "credit_usd": credit,
        "adjustment_usd": adjustment,
        "tax_usd": tax,
        "net_usd": net,
        "provider_http_request_id": request_id,
    }


def _document(*, lines: list[dict[str, object]] | None = None, total: str = "1.250000") -> dict[str, object]:
    return {
        "schema_version": "deepr-provider-billing-import-v1",
        "kind": "deepr.costs.provider_billing_import",
        "provider": "openai",
        "billing_scope": {"scope_ref": "project-primary", "account_id": "account-1"},
        "statement": {
            "statement_id": "statement-2026-07",
            "status": "final",
            "complete": True,
            "period_start": "2026-07-01T00:00:00+00:00",
            "period_end": "2026-08-01T00:00:00+00:00",
            "currency": "USD",
            "source_posture": "operator_normalized",
            "net_total_usd": total,
        },
        "lines": lines or [_line()],
    }


def _write_document(path: Path, document: dict[str, object]) -> None:
    path.write_text(json.dumps(document), encoding="utf-8")


def _write_ledger(path: Path, *events: CostLedgerEvent) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(event.to_dict()) + "\n" for event in events), encoding="utf-8")


def _event(*, request_id: str = "req-1", cost: float = 1.25, key: str = "job:one:completion") -> CostLedgerEvent:
    return CostLedgerEvent(
        operation="research_completion",
        provider="openai",
        cost_usd=cost,
        timestamp=datetime(2026, 7, 1, 1, 2, tzinfo=UTC),
        request_id=request_id,
        idempotency_key=key,
        metadata={"provider_http_request_id": request_id, "client_correlation_id": "job-one"},
    )


def _account_evidence(
    observed_at: datetime,
    *,
    provider: str = "openai",
    freeze_id: str = "freeze-current",
    hard_limit: str = "10.00",
    source_sha256: str = "1" * 64,
    reconciliation_sha256: str = "2" * 64,
) -> PaidApiAccountEvidence:
    return PaidApiAccountEvidence(
        schema_version="deepr-paid-api-account-evidence-v1",
        kind="deepr.costs.paid_api_account_evidence",
        provider=provider,
        account_id=f"test-{provider}-account",
        scope_ref=f"test-{provider}-scope",
        credential_fingerprint="sha256:" + "3" * 64,
        freeze_id=freeze_id,
        freeze_frozen_at=observed_at.isoformat(),
        observed_at=observed_at.isoformat(),
        valid_until=(observed_at + timedelta(hours=1)).isoformat(),
        source_posture="provider_api",
        source_evidence_sha256=source_sha256,
        billing_reconciliation_sha256=reconciliation_sha256,
        control_mode="hard_monthly_limit",
        currency="USD",
        overage_enabled=False,
        hard_monthly_limit_usd=hard_limit,
    )


def _store_authenticated_account_evidence(
    root: Path,
    observed_at: datetime,
    *,
    provider: str = "openai",
) -> tuple[str, ProviderAccountEvidenceStore]:
    source = root.parent / f"{provider}-account-bill.json"
    document = _document(lines=[_line(charge="0", net="0")], total="0")
    document["provider"] = provider
    document["billing_scope"] = {
        "scope_ref": f"test-{provider}-scope",
        "account_id": f"test-{provider}-account",
    }
    document["statement"]["period_start"] = (observed_at - timedelta(days=365)).isoformat()
    document["statement"]["period_end"] = (observed_at + timedelta(hours=1)).isoformat()
    document["statement"]["source_posture"] = "provider_api"
    document["lines"][0]["usage_start"] = observed_at.isoformat()
    document["lines"][0]["usage_end"] = observed_at.isoformat()
    _write_document(source, document)
    loaded = load_billing_import(source)
    report = reconcile_billing(loaded, locked_ledger_snapshot(CostLedger()))
    BillingEvidenceStore(root).store(loaded, report)
    reconciliation_sha256 = next((root / "reconciliations_by_hash").glob("*.json")).stem
    store = ProviderAccountEvidenceStore(root)
    evidence_id, _path = store.store(
        _account_evidence(
            observed_at,
            provider=provider,
            source_sha256=loaded.source_sha256,
            reconciliation_sha256=reconciliation_sha256,
        )
    )
    return evidence_id, store


def _budget_document() -> dict[str, object]:
    return {
        "monthly_limit": 10.0,
        "paid_api_frozen": False,
        "paid_api_authorization": {
            "authority": "verified_by_deepr",
            "evidence_ids": ["verified-account-control"],
            "valid_until": "2099-01-01T00:00:00+00:00",
        },
    }


def test_exact_receipt_match_is_clean(tmp_path: Path) -> None:
    source = tmp_path / "bill.json"
    ledger = tmp_path / "ledger.jsonl"
    _write_document(source, _document())
    _write_ledger(ledger, _event())

    loaded = load_billing_import(source)
    report = reconcile_billing(loaded, read_only_ledger_snapshot(ledger))

    assert report.status == "clean"
    assert report.freeze_required is False
    assert report.gross_unexplained_positive_microusd == 0
    assert report.match_counts.matched_positive_lines == 1
    assert report.matches[0].basis == "provider_http_request_id"


def test_preview_is_write_free_even_when_cost_directories_do_not_exist(tmp_path: Path) -> None:
    source = tmp_path / "bill.json"
    ledger = tmp_path / "missing" / "ledger.jsonl"
    store = tmp_path / "missing-store"
    budget = tmp_path / "missing-budget" / "budget.json"
    _write_document(source, _document())
    before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))

    report = reconcile_billing_file(
        source,
        ledger_path=ledger,
        store_root=store,
        budget_path=budget,
    )

    after = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))
    assert report.status == "drift"
    assert before == after
    assert not store.exists()
    assert not budget.exists()


def test_preview_deduplicates_identical_cross_root_idempotency_events(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    event = _event()
    _write_ledger(first, event)
    _write_ledger(second, event)
    monkeypatch.setattr(billing_module, "well_known_ledger_paths", lambda: (first, second))

    snapshot = read_only_ledger_snapshot()

    assert snapshot.events == (event,)


def test_preview_rejects_conflicting_cross_root_idempotency_events(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    _write_ledger(first, _event(cost=1.25))
    _write_ledger(second, _event(cost=2.0))
    monkeypatch.setattr(billing_module, "well_known_ledger_paths", lambda: (first, second))

    with pytest.raises(ProviderBillingValidationError, match="conflicting cross-root"):
        read_only_ledger_snapshot()


def test_preview_retries_when_well_known_path_set_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    _write_ledger(first, _event(key="job:first:completion"))
    _write_ledger(second, _event(key="job:second:completion", request_id="req-2"))
    calls = 0

    def changing_paths() -> tuple[Path, ...]:
        nonlocal calls
        calls += 1
        return (first,) if calls == 1 else (first, second)

    monkeypatch.setattr(billing_module, "well_known_ledger_paths", changing_paths)

    snapshot = read_only_ledger_snapshot()

    assert len(snapshot.events) == 2
    assert calls >= 4


def test_preview_bounds_second_stability_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = tmp_path / "ledger.jsonl"
    _write_ledger(ledger, _event())
    original_read = billing_module._bounded_ledger_read
    monkeypatch.setattr(billing_module, "_MAX_LEDGER_BYTES", ledger.stat().st_size + 1)
    calls = 0

    def grow_after_first_read(path: Path) -> bytes:
        nonlocal calls
        payload = original_read(path)
        calls += 1
        if calls == 1:
            path.write_bytes(payload + b"xx")
        return payload

    monkeypatch.setattr(billing_module, "_bounded_ledger_read", grow_after_first_read)

    with pytest.raises(ProviderBillingValidationError, match="read-only audit limit"):
        read_only_ledger_snapshot(ledger)


def test_duplicate_keys_and_secret_fields_are_rejected_without_echo(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"schema_version":"a","schema_version":"b"}', encoding="utf-8")
    with pytest.raises(ProviderBillingValidationError, match="duplicate"):
        load_billing_import(duplicate)

    secret = tmp_path / "secret.json"
    document = _document()
    document["api_key"] = "not-echoed-secret"
    _write_document(secret, document)
    with pytest.raises(ProviderBillingValidationError) as error:
        load_billing_import(secret)
    assert "not-echoed-secret" not in str(error.value)


@pytest.mark.parametrize(
    ("mutate", "error_fragment"),
    [
        (lambda document: document["statement"].__setitem__("net_total_usd", 1.25), "validation"),
        (lambda document: document["statement"].__setitem__("period_start", "2026-07-01"), "validation"),
        (lambda document: document["lines"][0].__setitem__("net_usd", "1.24"), "validation"),
        (lambda document: document.__setitem__("unknown", True), "validation"),
    ],
)
def test_closed_contract_rejects_invalid_money_time_sums_and_fields(
    tmp_path: Path,
    mutate,
    error_fragment: str,
) -> None:
    source = tmp_path / "invalid.json"
    document = _document()
    mutate(document)
    _write_document(source, document)

    with pytest.raises(ProviderBillingValidationError, match=error_fragment):
        load_billing_import(source)


def test_credits_never_offset_an_unmatched_positive_charge(tmp_path: Path) -> None:
    source = tmp_path / "bill.json"
    lines = [
        _line(line_id="charge", charge="2.000000", net="2.000000", request_id="unknown"),
        _line(line_id="credit", charge="0", credit="-2.000000", net="-2.000000", request_id=""),
    ]
    _write_document(source, _document(lines=lines, total="0"))

    report = reconcile_billing_file(source, ledger_path=tmp_path / "missing.jsonl")

    assert report.status == "drift"
    assert report.provider_net_microusd == 0
    assert report.gross_unexplained_positive_microusd == 2_000_000
    assert report.credits_and_negative_adjustments_microusd == 2_000_000


def test_duplicate_local_receipt_identity_is_ambiguous(tmp_path: Path) -> None:
    source = tmp_path / "bill.json"
    ledger = tmp_path / "ledger.jsonl"
    _write_document(source, _document())
    _write_ledger(
        ledger,
        _event(key="job:one:completion"),
        _event(key="job:two:completion"),
    )

    report = reconcile_billing_file(source, ledger_path=ledger)

    assert report.status == "ambiguous"
    assert report.match_counts.ambiguous_positive_lines == 1
    assert report.gross_unexplained_positive_microusd == 1_250_000


@pytest.mark.parametrize(
    ("field", "value", "status"),
    [
        ("status", "provisional", "provisional"),
        ("complete", False, "incomplete"),
        ("currency", "EUR", "unsupported_currency"),
    ],
)
def test_nonfinal_or_unsupported_statements_never_pass(
    tmp_path: Path,
    field: str,
    value: object,
    status: str,
) -> None:
    source = tmp_path / "bill.json"
    ledger = tmp_path / "ledger.jsonl"
    document = _document()
    document["statement"][field] = value
    _write_document(source, document)
    _write_ledger(ledger, _event())

    report = reconcile_billing_file(source, ledger_path=ledger)

    assert report.status == status
    assert report.freeze_required is True


def test_apply_drift_persists_typed_freeze_and_sanitized_evidence(tmp_path: Path) -> None:
    source = tmp_path / "bill.json"
    budget = tmp_path / "budget.json"
    store = tmp_path / "provider-billing"
    _write_document(source, _document())
    _write_document(budget, _budget_document())

    report = reconcile_billing_file(
        source,
        apply=True,
        ledger_path=tmp_path / "missing-ledger.jsonl",
        store_root=store,
        budget_path=budget,
    )

    persisted_budget = json.loads(budget.read_text(encoding="utf-8"))
    assert report.status == "drift"
    assert report.freeze_applied is True
    assert persisted_budget["paid_api_frozen"] is True
    assert persisted_budget["freeze_kind"] == "billing_divergence"
    assert persisted_budget["freeze_id"].startswith("billing_")
    assert "paid_api_authorization" not in persisted_budget
    assert len(list((store / "imports").glob("*.json"))) == 1
    assert len(list((store / "reconciliations").glob("*.json"))) == 1


def test_clean_apply_stores_evidence_but_never_unfreezes(tmp_path: Path) -> None:
    source = tmp_path / "bill.json"
    ledger = tmp_path / "ledger.jsonl"
    budget = tmp_path / "budget.json"
    store = tmp_path / "provider-billing"
    _write_document(source, _document())
    _write_ledger(ledger, _event())
    frozen_budget = _budget_document()
    frozen_budget.update(
        {
            "paid_api_frozen": True,
            "freeze_reason": "incident review",
            "freeze_id": "freeze_incident",
            "freeze_kind": "manual",
            "frozen_at": "2026-07-01T00:00:00+00:00",
        }
    )
    _write_document(budget, frozen_budget)

    report = reconcile_billing_file(
        source,
        apply=True,
        ledger_path=ledger,
        store_root=store,
        budget_path=budget,
    )

    persisted = json.loads(budget.read_text(encoding="utf-8"))
    assert report.status == "clean"
    assert report.freeze_applied is False
    assert persisted["paid_api_frozen"] is True
    assert persisted["freeze_id"] == "freeze_incident"


def test_apply_validation_failure_freezes_before_returning(tmp_path: Path) -> None:
    source = tmp_path / "bill.json"
    budget = tmp_path / "budget.json"
    _write_document(source, _document())
    _write_document(budget, _budget_document())

    with pytest.raises(ProviderBillingValidationError, match="expected provider"):
        reconcile_billing_file(
            source,
            apply=True,
            expect_provider="xai",
            budget_path=budget,
            store_root=tmp_path / "store",
            ledger_path=tmp_path / "ledger.jsonl",
        )

    persisted = json.loads(budget.read_text(encoding="utf-8"))
    assert persisted["paid_api_frozen"] is True
    assert persisted["freeze_kind"] == "account_identity_mismatch"


def test_immutable_store_is_idempotent_and_rejects_collisions(tmp_path: Path) -> None:
    source = tmp_path / "bill.json"
    ledger = tmp_path / "ledger.jsonl"
    _write_document(source, _document())
    _write_ledger(ledger, _event())
    loaded = load_billing_import(source)
    report = reconcile_billing(loaded, read_only_ledger_snapshot(ledger))
    store = BillingEvidenceStore(tmp_path / "store")

    paths = store.store(loaded, report)
    assert store.store(loaded, report) == paths
    paths[0].write_text("different", encoding="utf-8")
    with pytest.raises(ProviderBillingStorageError, match="different content"):
        store.store(loaded, report)


def test_self_asserted_account_evidence_never_authorizes_in_production(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_at = datetime.now(UTC)
    store = ProviderAccountEvidenceStore(tmp_path / "store")
    evidence_id, _path = store.store(_account_evidence(observed_at))
    monkeypatch.setattr(
        account_controls_module,
        "_verify_authenticated_account_evidence_source",
        _PRODUCTION_SOURCE_VERIFIER,
    )

    with pytest.raises(ProviderAccountControlError, match="no authenticated provider-specific"):
        verify_paid_api_authorization(
            [evidence_id],
            expected_freeze_id="freeze-current",
            expected_frozen_at=observed_at,
            monthly_limit_usd=5.0,
            requested_provider=None,
            store_root=tmp_path / "store",
        )


def test_authenticated_account_evidence_binds_freeze_provider_and_hard_limit(tmp_path: Path) -> None:
    observed_at = datetime.now(UTC)
    evidence_id, _store = _store_authenticated_account_evidence(tmp_path / "store", observed_at)

    authorization = verify_paid_api_authorization(
        [evidence_id],
        expected_freeze_id="freeze-current",
        expected_frozen_at=observed_at,
        monthly_limit_usd=5.0,
        requested_provider="openai",
        store_root=tmp_path / "store",
    )

    assert authorization.providers == ("openai",)
    assert authorization.hard_monthly_limit_usd == 10.0
    assert authorization.evidence_ids == (evidence_id,)

    with pytest.raises(ProviderAccountControlError, match="current freeze ID"):
        verify_paid_api_authorization(
            [evidence_id],
            expected_freeze_id="freeze-other",
            expected_frozen_at=observed_at,
            monthly_limit_usd=5.0,
            requested_provider="openai",
            store_root=tmp_path / "store",
        )
    with pytest.raises(ProviderAccountControlError, match="requested provider"):
        verify_paid_api_authorization(
            [evidence_id],
            expected_freeze_id="freeze-current",
            expected_frozen_at=observed_at,
            monthly_limit_usd=5.0,
            requested_provider="xai",
            store_root=tmp_path / "store",
        )
    with pytest.raises(ProviderAccountControlError, match="exceeds the provider account"):
        verify_paid_api_authorization(
            [evidence_id],
            expected_freeze_id="freeze-current",
            expected_frozen_at=observed_at,
            monthly_limit_usd=11.0,
            requested_provider="openai",
            store_root=tmp_path / "store",
        )


def test_authenticated_evidence_still_blocks_without_current_identity_resolver(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_at = datetime.now(UTC)
    evidence_id, _store = _store_authenticated_account_evidence(tmp_path / "store", observed_at)
    monkeypatch.setattr(
        account_controls_module,
        "_resolve_current_provider_account_binding",
        _PRODUCTION_BINDING_RESOLVER,
    )

    with pytest.raises(ProviderAccountControlError, match="identity resolver"):
        verify_paid_api_authorization(
            [evidence_id],
            expected_freeze_id="freeze-current",
            expected_frozen_at=observed_at,
            monthly_limit_usd=5.0,
            requested_provider=None,
            store_root=tmp_path / "store",
        )


@pytest.mark.parametrize(
    ("account_id", "scope_ref", "credential_fingerprint"),
    [
        ("wrong-account", "test-openai-scope", "sha256:" + "3" * 64),
        ("test-openai-account", "wrong-scope", "sha256:" + "3" * 64),
        ("test-openai-account", "test-openai-scope", "sha256:" + "4" * 64),
    ],
)
def test_current_account_scope_and_credential_must_match_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    account_id: str,
    scope_ref: str,
    credential_fingerprint: str,
) -> None:
    observed_at = datetime.now(UTC)
    evidence_id, _store = _store_authenticated_account_evidence(tmp_path / "store", observed_at)
    monkeypatch.setattr(
        account_controls_module,
        "_resolve_current_provider_account_binding",
        lambda provider: ProviderAccountBinding(
            provider=provider,
            account_id=account_id,
            scope_ref=scope_ref,
            credential_fingerprint=credential_fingerprint,
        ),
    )

    with pytest.raises(ProviderAccountControlError, match="does not match"):
        verify_paid_api_authorization(
            [evidence_id],
            expected_freeze_id="freeze-current",
            expected_frozen_at=observed_at,
            monthly_limit_usd=5.0,
            requested_provider="openai",
            store_root=tmp_path / "store",
        )


def test_recovery_rejects_missing_nonclean_and_stale_reconciliation(tmp_path: Path) -> None:
    observed_at = datetime.now(UTC)
    root = tmp_path / "store"
    evidence_id, store = _store_authenticated_account_evidence(root, observed_at - timedelta(hours=2))
    old_evidence = store.load(evidence_id)
    stale_evidence_id, _path = store.store(
        _account_evidence(
            observed_at,
            source_sha256=old_evidence.source_evidence_sha256,
            reconciliation_sha256=old_evidence.billing_reconciliation_sha256,
        )
    )

    with pytest.raises(ProviderAccountControlError, match="stale"):
        verify_paid_api_authorization(
            [stale_evidence_id],
            expected_freeze_id="freeze-current",
            expected_frozen_at=observed_at,
            monthly_limit_usd=5.0,
            requested_provider="openai",
            store_root=root,
        )

    missing_id, _path = store.store(_account_evidence(observed_at, reconciliation_sha256="f" * 64))
    with pytest.raises(ProviderAccountControlError, match="missing or unreadable"):
        verify_paid_api_authorization(
            [missing_id],
            expected_freeze_id="freeze-current",
            expected_frozen_at=observed_at,
            monthly_limit_usd=5.0,
            requested_provider="openai",
            store_root=root,
        )

    clean_path = root / "reconciliations_by_hash" / f"{old_evidence.billing_reconciliation_sha256}.json"
    nonclean = json.loads(clean_path.read_text(encoding="utf-8"))
    nonclean["status"] = "drift"
    nonclean["freeze_required"] = True
    payload = json.dumps(nonclean, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    nonclean_digest = hashlib.sha256(payload).hexdigest()
    (root / "reconciliations_by_hash" / f"{nonclean_digest}.json").write_bytes(payload + b"\n")
    nonclean_id, _path = store.store(
        _account_evidence(
            observed_at,
            source_sha256=old_evidence.source_evidence_sha256,
            reconciliation_sha256=nonclean_digest,
        )
    )
    with pytest.raises(ProviderAccountControlError, match="not final, complete, clean"):
        verify_paid_api_authorization(
            [nonclean_id],
            expected_freeze_id="freeze-current",
            expected_frozen_at=observed_at,
            monthly_limit_usd=5.0,
            requested_provider="openai",
            store_root=root,
        )


def test_recovery_rejects_reconciliation_when_current_ledger_changed(tmp_path: Path) -> None:
    observed_at = datetime.now(UTC)
    root = tmp_path / "store"
    evidence_id, _store = _store_authenticated_account_evidence(root, observed_at)
    CostLedger().record_event(
        operation="new-paid-event",
        provider="openai",
        cost_usd=0.25,
        idempotency_key="new-paid-event",
    )

    with pytest.raises(ProviderAccountControlError, match="current strict ledger snapshot"):
        verify_paid_api_authorization(
            [evidence_id],
            expected_freeze_id="freeze-current",
            expected_frozen_at=observed_at,
            monthly_limit_usd=5.0,
            requested_provider=None,
            store_root=root,
        )


def test_recovery_recomputes_instead_of_trusting_a_clean_status_field(tmp_path: Path) -> None:
    observed_at = datetime.now(UTC)
    root = tmp_path / "store"
    evidence_id, store = _store_authenticated_account_evidence(root, observed_at)
    evidence = store.load(evidence_id)
    report_path = root / "reconciliations_by_hash" / f"{evidence.billing_reconciliation_sha256}.json"
    asserted_clean = json.loads(report_path.read_text(encoding="utf-8"))
    asserted_clean["provider_net_microusd"] = 1
    payload = json.dumps(asserted_clean, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    asserted_digest = hashlib.sha256(payload).hexdigest()
    (root / "reconciliations_by_hash" / f"{asserted_digest}.json").write_bytes(payload + b"\n")
    asserted_evidence_id, _path = store.store(
        _account_evidence(
            observed_at,
            source_sha256=evidence.source_evidence_sha256,
            reconciliation_sha256=asserted_digest,
        )
    )

    with pytest.raises(ProviderAccountControlError, match="clean status was not reproduced"):
        verify_paid_api_authorization(
            [asserted_evidence_id],
            expected_freeze_id="freeze-current",
            expected_frozen_at=observed_at,
            monthly_limit_usd=5.0,
            store_root=root,
        )


def test_authorization_fails_if_the_normalized_reconciliation_source_disappears(tmp_path: Path) -> None:
    observed_at = datetime.now(UTC)
    root = tmp_path / "store"
    evidence_id, store = _store_authenticated_account_evidence(root, observed_at)
    evidence = store.load(evidence_id)
    (root / "imports" / f"{evidence.source_evidence_sha256}.json").unlink()

    with pytest.raises(ProviderAccountControlError, match="normalized billing import is missing"):
        verify_paid_api_authorization(
            [evidence_id],
            expected_freeze_id="freeze-current",
            expected_frozen_at=observed_at,
            monthly_limit_usd=5.0,
            requested_provider="openai",
            store_root=root,
        )


def test_capacity_classes_are_not_reconciled_as_metered_api_spend(tmp_path: Path) -> None:
    source = tmp_path / "bill.json"
    ledger = tmp_path / "ledger.jsonl"
    prepaid = _line(charge="30.000000", net="30.000000")
    prepaid["capacity_class"] = "prepaid_plan"
    document = _document(lines=[prepaid], total="30.000000")
    _write_document(source, document)
    _write_ledger(ledger, _event(cost=30.0))

    report = reconcile_billing_file(source, ledger_path=ledger)

    assert report.status == "incomplete"
    assert report.api_metered_net_microusd == 0
    assert report.prepaid_plan_net_microusd == 30_000_000
    assert report.net_drift_microusd == -30_000_000
    assert report.gross_unexplained_positive_microusd == 0
    assert report.matches == []
    assert len(report.unmatched_ledger_events) == 1


def test_unknown_positive_capacity_stays_fail_closed_even_with_receipt_match(tmp_path: Path) -> None:
    source = tmp_path / "bill.json"
    ledger = tmp_path / "ledger.jsonl"
    unknown = _line()
    unknown["capacity_class"] = "unknown"
    _write_document(source, _document(lines=[unknown]))
    _write_ledger(ledger, _event())

    report = reconcile_billing_file(source, ledger_path=ledger)

    assert report.status == "drift"
    assert report.unknown_net_microusd == 1_250_000
    assert report.gross_unexplained_positive_microusd == 1_250_000
    assert report.matches == []
    assert report.freeze_required is True


def test_runtime_payloads_validate_against_published_schemas(tmp_path: Path) -> None:
    source = tmp_path / "bill.json"
    ledger = tmp_path / "ledger.jsonl"
    _write_document(source, _document())
    _write_ledger(ledger, _event())
    loaded = load_billing_import(source)
    report = reconcile_billing(loaded, read_only_ledger_snapshot(ledger))
    schema_root = Path(__file__).resolve().parents[3] / "docs" / "schemas"
    import_schema = json.loads((schema_root / "provider-billing-import-v1.json").read_text(encoding="utf-8"))
    report_schema = json.loads((schema_root / "provider-billing-reconciliation-v1.json").read_text(encoding="utf-8"))
    account_schema = json.loads((schema_root / "paid-api-account-evidence-v1.json").read_text(encoding="utf-8"))

    Draft202012Validator(import_schema, format_checker=FormatChecker()).validate(
        loaded.document.model_dump(mode="json")
    )
    Draft202012Validator(report_schema, format_checker=FormatChecker()).validate(report.model_dump(mode="json"))
    Draft202012Validator(account_schema, format_checker=FormatChecker()).validate(
        _account_evidence(datetime.now(UTC)).model_dump(mode="json")
    )


def test_source_hash_changes_but_normalized_hash_is_stable_for_whitespace(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    document = _document()
    first.write_text(json.dumps(document, separators=(",", ":")), encoding="utf-8")
    second.write_text(json.dumps(deepcopy(document), indent=4), encoding="utf-8")

    first_loaded = load_billing_import(first)
    second_loaded = load_billing_import(second)

    assert first_loaded.source_sha256 != second_loaded.source_sha256
    assert first_loaded.normalized_sha256 == second_loaded.normalized_sha256
