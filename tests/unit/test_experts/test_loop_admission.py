"""Tests for verified loop admission contracts."""

from __future__ import annotations

from deepr.experts.loop_admission import (
    LoopAdmissionContract,
    get_loop_admission_contract,
    known_loop_admission_contracts,
)


def test_contract_reports_missing_requirements():
    contract = LoopAdmissionContract(
        loop_type="gap_fill",
        repeat_demand=True,
        automated_verification=False,
        explicit_budget_capacity=True,
        failure_diagnosis_state=False,
        verifier="planned_gap_closure",
    )

    assert contract.admitted is False
    assert contract.status == "supervised"
    assert contract.missing_requirements == ["automated_verification", "failure_diagnosis_state"]
    assert contract.to_dict()["missing_requirements"] == ["automated_verification", "failure_diagnosis_state"]


def test_known_contracts_keep_gap_fill_supervised():
    contracts = known_loop_admission_contracts()

    assert contracts["sync"]["status"] == "admitted"
    assert contracts["reflection"]["status"] == "admitted"
    assert contracts["health_check"]["status"] == "admitted"
    assert contracts["gap_fill"]["status"] == "supervised"
    assert contracts["gap_fill"]["missing_requirements"] == ["automated_verification"]


def test_get_unknown_contract_returns_none():
    assert get_loop_admission_contract("unknown") is None
