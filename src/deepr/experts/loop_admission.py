"""Admission contracts for verified expert loops."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

ADMISSION_REQUIREMENTS = (
    "repeat_demand",
    "automated_verification",
    "explicit_budget_capacity",
    "failure_diagnosis_state",
)


@dataclass(frozen=True)
class LoopAdmissionContract:
    """Workflow gates required before an expert surface is autonomous."""

    loop_type: str
    repeat_demand: bool
    automated_verification: bool
    explicit_budget_capacity: bool
    failure_diagnosis_state: bool
    verifier: str
    notes: str = ""

    @property
    def admitted(self) -> bool:
        return all(
            (
                self.repeat_demand,
                self.automated_verification,
                self.explicit_budget_capacity,
                self.failure_diagnosis_state,
            )
        )

    @property
    def status(self) -> str:
        return "admitted" if self.admitted else "supervised"

    @property
    def missing_requirements(self) -> list[str]:
        return [requirement for requirement in ADMISSION_REQUIREMENTS if not bool(getattr(self, requirement))]

    def to_dict(self) -> dict[str, Any]:
        return {
            "loop_type": self.loop_type,
            "status": self.status,
            "admitted": self.admitted,
            "repeat_demand": self.repeat_demand,
            "automated_verification": self.automated_verification,
            "explicit_budget_capacity": self.explicit_budget_capacity,
            "failure_diagnosis_state": self.failure_diagnosis_state,
            "missing_requirements": self.missing_requirements,
            "verifier": self.verifier,
            "notes": self.notes,
        }


KNOWN_LOOP_ADMISSION_CONTRACTS: dict[str, LoopAdmissionContract] = {
    "sync": LoopAdmissionContract(
        loop_type="sync",
        repeat_demand=True,
        automated_verification=True,
        explicit_budget_capacity=True,
        failure_diagnosis_state=True,
        verifier="absorb_gates",
        notes="Subscribed-topic sync repeats and records accepted or rejected knowledge changes.",
    ),
    "reflection": LoopAdmissionContract(
        loop_type="reflection",
        repeat_demand=True,
        automated_verification=True,
        explicit_budget_capacity=True,
        failure_diagnosis_state=True,
        verifier="reflection_report",
        notes="Reflection records verifier outcome and follow-up absorption metrics.",
    ),
    "health_check": LoopAdmissionContract(
        loop_type="health_check",
        repeat_demand=True,
        automated_verification=True,
        explicit_budget_capacity=True,
        failure_diagnosis_state=True,
        verifier="health_check",
        notes="Health audits produce typed action plans and stop reasons before any corrective work.",
    ),
    "gap_fill": LoopAdmissionContract(
        loop_type="gap_fill",
        repeat_demand=True,
        automated_verification=False,
        explicit_budget_capacity=True,
        failure_diagnosis_state=True,
        verifier="planned_gap_closure",
        notes="Gap fill remains supervised until gap-closure verifier evidence is recorded.",
    ),
}


def known_loop_admission_contracts() -> dict[str, dict[str, Any]]:
    return {loop_type: contract.to_dict() for loop_type, contract in KNOWN_LOOP_ADMISSION_CONTRACTS.items()}


def get_loop_admission_contract(loop_type: str) -> LoopAdmissionContract | None:
    return KNOWN_LOOP_ADMISSION_CONTRACTS.get(loop_type)
