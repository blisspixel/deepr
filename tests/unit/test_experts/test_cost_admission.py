"""Fail-closed soft cost admission contracts."""

from __future__ import annotations

import pytest

from deepr.experts.cost_admission import admit_soft_cost_operation
from deepr.experts.cost_safety import reset_cost_safety_manager


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPR_COST_DATA_DIR", str(tmp_path / "costs"))
    reset_cost_safety_manager()
    yield
    reset_cost_safety_manager()


def test_admit_soft_cost_operation_allows_within_budget():
    manager, estimate, reason = admit_soft_cost_operation(
        session_id="unit",
        operation_type="unit_op",
        estimated_cost=0.01,
    )
    assert manager is not None
    assert estimate == pytest.approx(0.01)
    assert reason is None


def test_admit_soft_cost_operation_fails_closed_when_manager_raises(monkeypatch):
    def _boom():
        raise RuntimeError("ledger unavailable")

    monkeypatch.setattr("deepr.experts.cost_safety.get_cost_safety_manager", _boom)
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

    monkeypatch.setattr(
        "deepr.experts.cost_admission.admit_soft_cost_operation",
        lambda **_kwargs: (None, 0.02, "cost admission unavailable: test"),
    )
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
