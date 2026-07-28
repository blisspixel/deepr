"""Spend-truth regression tests: the display, the gate, and doctor must agree.

A $37.79 campaign once ran while `deepr budget status` showed $0.00, because
the display read only the session counter while spend from other entry points
landed in the canonical ledger. The display must show the same reconciled
number the approval gate uses, and `deepr doctor` must flag over-budget state
and orphaned spend loudly.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from click.testing import CliRunner

from deepr.cli.commands import budget as budget_module
from deepr.cli.commands import doctor as doctor_module
from deepr.observability.cost_ledger import CostLedger


def _monthly_exposure(settled: float, *, active: float = 0.0) -> SimpleNamespace:
    return SimpleNamespace(
        daily_settled_cost=settled,
        weekly_settled_cost=settled,
        monthly_settled_cost=settled,
        total_settled_cost=settled,
        active_cost=active,
        unresolved_cost=0.0,
        unresolved_count=0,
    )


def test_budget_status_shows_ledger_reconciled_spend() -> None:
    with (
        patch.object(
            budget_module, "load_budget_config", return_value={"monthly_limit": 10.0, "monthly_spending": 0.0}
        ),
        patch.object(budget_module, "resolve_spend_caps", return_value={"monthly": 10.0}),
        patch.object(budget_module, "_atomic_monthly_exposure", return_value=_monthly_exposure(38.50)),
    ):
        result = CliRunner().invoke(budget_module.budget, ["status"])

    # The session counter says $0.00; the display must show the ledger number.
    assert "$38.50 / $10.00" in result.output
    assert "Over hard ceiling by: $28.50" in result.output
    assert "Paid API blocked: monthly hard ceiling exceeded" in result.output
    assert "never hit the session counter" in result.output
    assert "costs doctor" in result.output


def test_budget_status_no_divergence_note_when_counter_current() -> None:
    with (
        patch.object(
            budget_module, "load_budget_config", return_value={"monthly_limit": 10.0, "monthly_spending": 3.0}
        ),
        patch.object(budget_module, "resolve_spend_caps", return_value={"monthly": 10.0}),
        patch.object(budget_module, "_atomic_monthly_exposure", return_value=_monthly_exposure(3.0)),
    ):
        result = CliRunner().invoke(budget_module.budget, ["status"])

    assert "$3.00 / $10.00" in result.output
    assert "never hit the session counter" not in result.output


def test_doctor_flags_over_budget_from_ledger() -> None:
    with (
        patch(
            "deepr.cli.commands.budget.load_budget_config",
            return_value={"monthly_limit": 10.0, "monthly_spending": 0.0},
        ),
        patch("deepr.cli.commands.budget._ledger_month_spend", return_value=38.50),
    ):
        checks = doctor_module.check_spend_integrity()

    over_budget = next(c for c in checks if c.name == "Monthly spend vs budget")
    assert over_budget.passed is False
    assert "OVER BUDGET" in over_budget.message
    assert any("ledger is canonical" in d for d in over_budget.details)


def test_doctor_passes_when_under_budget_and_counter_current() -> None:
    with (
        patch(
            "deepr.cli.commands.budget.load_budget_config",
            return_value={"monthly_limit": 10.0, "monthly_spending": 2.0},
        ),
        patch("deepr.cli.commands.budget._ledger_month_spend", return_value=2.0),
    ):
        checks = doctor_module.check_spend_integrity()

    over_budget = next(c for c in checks if c.name == "Monthly spend vs budget")
    assert over_budget.passed is True
    assert "$2.00" in over_budget.message


def test_doctor_flags_positive_spend_against_zero_ceiling() -> None:
    with (
        patch(
            "deepr.cli.commands.budget.load_budget_config",
            return_value={"monthly_limit": 0.0, "monthly_spending": 0.0},
        ),
        patch("deepr.cli.commands.budget._ledger_month_spend", return_value=1.25),
    ):
        checks = doctor_module.check_spend_integrity()

    over_budget = next(c for c in checks if c.name == "Monthly spend vs budget")
    assert over_budget.passed is False
    assert "OVER BUDGET: $1.25 spent against a $0.00/month budget" in over_budget.message


def test_doctor_artifact_audit_uses_configured_reports_root(tmp_path: Path, monkeypatch) -> None:
    reports = tmp_path / "configured-reports"
    (reports / "2026-07-27_topic_a7ae5c65").mkdir(parents=True)
    monkeypatch.setattr(doctor_module, "load_config", lambda: {"results_dir": str(reports)})
    CostLedger().record_event(
        operation="research",
        provider="openai",
        cost_usd=0.25,
        task_id="research_research-a7ae5c653d8c",
        idempotency_key="doctor-configured-report-root",
    )

    checks = doctor_module.check_spend_integrity()

    artifacts = next(c for c in checks if c.name == "Paid artifacts on disk")
    assert artifacts.passed is True
    assert "$0.25 matched" in artifacts.message


def test_doctor_artifact_audit_reports_unknown_for_malformed_ledger(tmp_path: Path, monkeypatch) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    monkeypatch.setattr(doctor_module, "load_config", lambda: {"results_dir": str(reports)})
    CostLedger().ledger_path.write_text('{"operation":', encoding="utf-8")

    checks = doctor_module.check_spend_integrity()

    artifacts = next(c for c in checks if c.name == "Paid artifacts on disk")
    assert artifacts.passed is False
    assert "UNKNOWN" in artifacts.message
    assert any("Paid API dispatch must remain blocked" in detail for detail in artifacts.details)
