"""Canonical ledger location must be stable, and spend queries must see it all.

The default ledger path was bare CWD-relative: every working directory minted
its own empty ledger, so a budget gate running from the "wrong" directory read
$0 spent and approved money it should have blocked. The default now falls back
to ~/.deepr/costs when no project-local ledger exists, and default-path spend
queries union both well-known locations so no recorded dollar is invisible.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from deepr.observability.cost_ledger import CostLedger, default_cost_data_dir


def test_bare_cwd_does_not_mint_a_fresh_ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPR_COST_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    fake_home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    assert default_cost_data_dir() == fake_home / ".deepr" / "costs"


def test_project_local_ledger_keeps_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPR_COST_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    local = tmp_path / "data" / "costs"
    local.mkdir(parents=True)
    (local / "cost_ledger.jsonl").write_text("", encoding="utf-8")

    assert default_cost_data_dir() == Path("data/costs")


def test_env_override_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPR_COST_DATA_DIR", str(tmp_path / "override"))
    assert default_cost_data_dir() == tmp_path / "override"


def test_default_ledger_unions_well_known_locations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPR_COST_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    fake_home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    # Spend recorded by a process that ran from the project root...
    project_ledger_dir = tmp_path / "data" / "costs"
    project_ledger_dir.mkdir(parents=True)
    CostLedger(ledger_path=project_ledger_dir / "cost_ledger.jsonl").record_event(
        operation="research_completion",
        provider="openai",
        cost_usd=5.0,
        idempotency_key="union-project",
    )
    # ...and spend recorded by a process anchored to the home ledger.
    home_ledger_dir = fake_home / ".deepr" / "costs"
    home_ledger_dir.mkdir(parents=True)
    CostLedger(ledger_path=home_ledger_dir / "cost_ledger.jsonl").record_event(
        operation="research_completion",
        provider="xai",
        cost_usd=2.0,
        idempotency_key="union-home",
    )

    # A default-path reader (the budget gate) must see BOTH.
    total = CostLedger().get_total_cost()
    assert total == pytest.approx(7.0)


def test_explicit_ledger_path_stays_isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPR_COST_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    other = tmp_path / "data" / "costs"
    other.mkdir(parents=True)
    (other / "cost_ledger.jsonl").write_text(
        "",
        encoding="utf-8",
    )
    CostLedger(ledger_path=other / "cost_ledger.jsonl").record_event(
        operation="research_completion",
        provider="openai",
        cost_usd=9.0,
        idempotency_key="isolated-other",
    )

    isolated = CostLedger(ledger_path=tmp_path / "mine.jsonl")
    assert isolated.get_total_cost() == 0.0


def test_budget_approval_fails_closed_when_ledger_unreadable(monkeypatch: pytest.MonkeyPatch) -> None:
    from deepr.cli.commands import budget as budget_module

    monkeypatch.setattr(budget_module, "_ledger_month_spend", lambda: None)
    monkeypatch.setattr(
        budget_module,
        "load_budget_config",
        lambda: {"monthly_limit": 100.0, "monthly_spending": 0.0},
    )
    # A tiny job under a generous budget would normally auto-approve; with the
    # canonical ledger unreadable it must require manual confirmation instead.
    assert budget_module.check_budget_approval(0.05) is False

    monkeypatch.setattr(
        budget_module,
        "load_budget_config",
        lambda: {"monthly_limit": 0, "monthly_spending": 0.0},
    )
    # Cautious mode's under-$1 convenience also fails closed.
    assert budget_module.check_budget_approval(0.05) is False
