"""Fail-closed soft cost admission contracts."""

from __future__ import annotations

import pytest

from deepr.experts.cost_admission import admit_soft_cost_operation, record_soft_cost
from deepr.experts.cost_safety import reset_cost_safety_manager


@pytest.fixture(autouse=True)
def _isolate():
    reset_cost_safety_manager()
    yield
    reset_cost_safety_manager()


def test_admit_soft_cost_operation_places_durable_marked_hold():
    manager, estimate, reason = admit_soft_cost_operation(
        session_id="unit",
        operation_type="unit_op",
        estimated_cost=0.01,
    )
    assert manager is not None
    assert estimate == pytest.approx(0.01)
    assert reason is None
    record_soft_cost(
        manager,
        actual_cost=0.0,
        provider="openai",
        model="gpt-5-mini",
        source="test.cost_admission",
    )


def test_admit_soft_cost_operation_fails_closed_when_reservation_raises(monkeypatch):
    monkeypatch.setattr(
        "deepr.experts.research_cost_gate.reserve_configured_cost_ceiling",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("ledger unavailable")),
    )
    manager, estimate, reason = admit_soft_cost_operation(
        session_id="unit",
        operation_type="unit_op",
        estimated_cost=0.05,
    )
    assert manager is None
    assert estimate == pytest.approx(0.05)
    assert reason is not None
    assert "unavailable" in reason


@pytest.mark.asyncio
async def test_citation_validator_fails_closed_when_admission_unavailable(monkeypatch):
    from deepr.core.contracts import Claim, Source, SupportClass, TrustClass
    from deepr.experts.citation_validator import CitationValidator

    async def _deny_admission(**_kwargs):
        raise RuntimeError("cost admission unavailable: test")

    monkeypatch.setattr("deepr.services.metered_call.execute_reserved_async_call", _deny_admission)
    validator = CitationValidator()
    source = Source.create(title="paper.md", trust_class=TrustClass.SECONDARY)
    claim = Claim(
        id="c1",
        statement="s",
        domain="test",
        confidence=0.5,
        sources=[source],
    )

    async def _never():
        raise AssertionError("paid client must not be constructed after failed admission")

    monkeypatch.setattr(validator, "_get_client", _never)
    results = await validator.validate_claims([claim], {"paper.md": "supporting text"})
    assert len(results) == 1
    assert results[0].support_class == SupportClass.UNCERTAIN
    assert "unavailable" in results[0].explanation
