"""Focused durability tests for paired plan-quota attempt accounting."""

from __future__ import annotations

import pytest

from deepr.backends.plan_quota.adapters import get_adapter
from deepr.backends.plan_quota.attempt_accounting import (
    DEFAULT_PLAN_ACCOUNTING_LOCK_TIMEOUT_SECONDS,
    AttemptAccountingError,
    AttemptAccountingRefusedError,
    record_plan_quota_attempt,
)
from deepr.backends.plan_quota.safety import AuthMode
from deepr.backends.quota_ledger import (
    QuotaEventType,
    QuotaLedger,
    QuotaLedgerDurabilityError,
)
from deepr.observability.cost_ledger import CostLedger


def _record(tmp_path, **overrides):
    arguments = {
        "attempt_id": "plan-quota:claude:fixture",
        "operation": "plan_quota_research",
        "model": None,
        "quota_ledger_path": tmp_path / "quota.jsonl",
        "cost_ledger_path": tmp_path / "cost.jsonl",
        "outcome": "success",
        "quota_event_type": QuotaEventType.USAGE_OBSERVED,
        "quota_units": 1.0,
        "vendor_dispatched": True,
        "detail": "fixture",
        "auth_mode": AuthMode.PLAN,
    }
    arguments.update(overrides)
    return record_plan_quota_attempt(get_adapter("claude"), **arguments)


def test_paired_accounting_requires_fsync_and_bounded_locks(monkeypatch, tmp_path):
    quota_calls = []
    cost_calls = []
    real_quota_record = QuotaLedger.record_event
    real_cost_record = CostLedger.record_event

    def quota_record(self, event, *, require_fsync=False):
        quota_calls.append((self._lock_timeout_seconds, require_fsync))
        return real_quota_record(self, event, require_fsync=require_fsync)

    def cost_record(self, *args, **kwargs):
        cost_calls.append(
            (
                self._lock_timeout_seconds,
                kwargs.get("lock_timeout_seconds"),
                kwargs.get("require_fsync"),
            )
        )
        return real_cost_record(self, *args, **kwargs)

    monkeypatch.setattr(QuotaLedger, "record_event", quota_record)
    monkeypatch.setattr(CostLedger, "record_event", cost_record)

    status = _record(tmp_path)

    expected = DEFAULT_PLAN_ACCOUNTING_LOCK_TIMEOUT_SECONDS
    assert status.quota_recorded is True
    assert status.cost_recorded is True
    assert quota_calls == [(expected, True)]
    assert cost_calls == [(expected, expected, True)]


def test_quota_durability_failure_preserves_paired_cost_partial_status(
    monkeypatch,
    tmp_path,
):
    def fail_quota_durability(self, event, *, require_fsync=False):
        assert require_fsync is True
        raise QuotaLedgerDurabilityError("quota ledger durability barrier failed")

    monkeypatch.setattr(QuotaLedger, "record_event", fail_quota_durability)

    with pytest.raises(AttemptAccountingError) as exc_info:
        _record(tmp_path)

    assert exc_info.value.status.quota_recorded is False
    assert exc_info.value.status.cost_recorded is True
    assert "QuotaLedgerDurabilityError" in str(exc_info.value)
    costs = CostLedger(tmp_path / "cost.jsonl").get_events()
    assert len(costs) == 1
    assert costs[0].cost_usd == 0.0
    assert costs[0].idempotency_key == "plan-quota:claude:fixture"


@pytest.mark.parametrize(
    ("backend_id", "auth_mode"),
    [
        ("opencode", AuthMode.UNKNOWN),
        ("codex", AuthMode.PLAN),
        ("claude", AuthMode.METERED),
    ],
)
def test_zero_cost_accounting_refuses_unproven_or_disabled_dispatches(tmp_path, backend_id, auth_mode):
    with pytest.raises(AttemptAccountingRefusedError, match="zero-cost accounting refused"):
        record_plan_quota_attempt(
            get_adapter(backend_id),
            attempt_id=f"plan-quota:{backend_id}:refused",
            operation="plan_quota_probe",
            model=None,
            quota_ledger_path=tmp_path / "quota.jsonl",
            cost_ledger_path=tmp_path / "cost.jsonl",
            outcome="success",
            quota_event_type=QuotaEventType.USAGE_OBSERVED,
            quota_units=1.0,
            vendor_dispatched=True,
            detail="must not be recorded",
            auth_mode=auth_mode,
        )

    assert not (tmp_path / "quota.jsonl").exists()
    assert not (tmp_path / "cost.jsonl").exists()
