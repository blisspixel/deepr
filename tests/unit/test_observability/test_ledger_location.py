"""Canonical ledger location must be stable, and spend queries must see it all.

The default ledger path was CWD-dependent: an existing project-local ledger
changed both the write root and reservation database. The default is now the
stable home cost root. Strict reads still include the source checkout's legacy
ledger so its historical spend cannot disappear during migration.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest

from deepr.experts.research_reservation_store import (
    ResearchReservationLimitExceeded,
    ResearchReservationStore,
    ResearchReservationStoreError,
)
from deepr.observability import cost_ledger as ledger_module
from deepr.observability.cost_ledger import (
    CostLedger,
    CostLedgerIdempotencyConflict,
    CostLedgerReadError,
    default_cost_data_dir,
)


def _seed_reservation(
    store: ResearchReservationStore,
    *,
    reservation_id: str,
    job_id: str,
    reserved_cost: float,
    provider_work_may_have_run: bool = True,
) -> None:
    with closing(sqlite3.connect(store.path)) as connection, connection:
        connection.execute(
            """
            INSERT INTO research_cost_reservations
                (reservation_id, job_id, reserved_cost, state, created_at, provider_work_may_have_run)
            VALUES (?, ?, ?, 'active', ?, ?)
            """,
            (
                reservation_id,
                job_id,
                reserved_cost,
                datetime.now(UTC).isoformat(),
                int(provider_work_may_have_run),
            ),
        )


def test_bare_cwd_does_not_mint_a_fresh_ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPR_COST_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    fake_home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    assert default_cost_data_dir() == fake_home / ".deepr" / "costs"


def test_project_local_ledger_never_changes_canonical_write_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPR_COST_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    fake_home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    local = tmp_path / "data" / "costs"
    local.mkdir(parents=True)
    (local / "cost_ledger.jsonl").write_text("", encoding="utf-8")

    assert default_cost_data_dir() == fake_home / ".deepr" / "costs"


def test_env_override_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPR_COST_DATA_DIR", str(tmp_path / "override"))
    assert default_cost_data_dir() == tmp_path / "override"


def test_relative_env_override_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPR_COST_DATA_DIR", "relative/costs")
    with pytest.raises(ValueError, match="absolute path"):
        default_cost_data_dir()


def test_relative_home_cost_root_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPR_COST_DATA_DIR", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: Path("relative-home")))

    with pytest.raises(ValueError, match="home path must be absolute"):
        default_cost_data_dir()


def test_unavailable_home_cost_root_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPR_COST_DATA_DIR", raising=False)

    def unavailable(_cls: type[Path]) -> Path:
        raise RuntimeError("home unavailable")

    monkeypatch.setattr(Path, "home", classmethod(unavailable))
    with pytest.raises(ValueError, match="home path is unavailable"):
        default_cost_data_dir()


def test_default_ledger_unions_well_known_locations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPR_COST_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    fake_home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(ledger_module, "_source_checkout_cost_data_dir", lambda: tmp_path / "data" / "costs")

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


def test_strict_accounting_rejects_malformed_sibling_ledger(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPR_COST_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    fake_home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(ledger_module, "_source_checkout_cost_data_dir", lambda: tmp_path / "data" / "costs")

    project_ledger_dir = tmp_path / "data" / "costs"
    project_ledger_dir.mkdir(parents=True)
    (project_ledger_dir / "cost_ledger.jsonl").write_text("not-json\n", encoding="utf-8")
    home_ledger_dir = fake_home / ".deepr" / "costs"
    home_ledger_dir.mkdir(parents=True)
    (home_ledger_dir / "cost_ledger.jsonl").write_text("", encoding="utf-8")

    with pytest.raises(CostLedgerReadError, match="malformed"):
        CostLedger().with_locked_accounting_events(list)


def test_strict_accounting_deduplicates_identical_cross_root_events(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPR_COST_DATA_DIR", raising=False)
    fake_home = tmp_path / "home"
    legacy_root = tmp_path / "checkout" / "data" / "costs"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(ledger_module, "_source_checkout_cost_data_dir", lambda: legacy_root)

    kwargs = {
        "operation": "research_completion",
        "provider": "openai",
        "cost_usd": 0.75,
        "idempotency_key": "cross-root-completion",
    }
    CostLedger(ledger_path=legacy_root / "cost_ledger.jsonl").record_event(**kwargs)
    CostLedger(ledger_path=fake_home / ".deepr" / "costs" / "cost_ledger.jsonl").record_event(**kwargs)

    strict_total = CostLedger().with_locked_accounting_events(lambda events: sum(event.cost_usd for event in events))
    assert strict_total == pytest.approx(0.75)


def test_long_lived_default_ledger_discovers_late_legacy_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPR_COST_DATA_DIR", raising=False)
    fake_home = tmp_path / "home"
    legacy_root = tmp_path / "checkout" / "data" / "costs"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(ledger_module, "_source_checkout_cost_data_dir", lambda: legacy_root)

    long_lived = CostLedger()
    kwargs = {
        "operation": "research_completion",
        "provider": "openai",
        "cost_usd": 0.75,
        "idempotency_key": "late-legacy-completion",
    }
    CostLedger(ledger_path=legacy_root / "cost_ledger.jsonl").record_event(**kwargs)

    assert long_lived.get_total_cost() == pytest.approx(0.75)
    assert long_lived.has_idempotency_key("late-legacy-completion") is True
    _event, created = long_lived.record_event(**kwargs)
    assert created is False
    assert not long_lived.ledger_path.exists()


def test_strict_discovery_does_not_create_missing_sibling_ledger(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPR_COST_DATA_DIR", raising=False)
    fake_home = tmp_path / "home"
    legacy_root = tmp_path / "checkout" / "data" / "costs"
    legacy_root.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(ledger_module, "_source_checkout_cost_data_dir", lambda: legacy_root)

    CostLedger().with_locked_accounting_events(list)

    assert not (legacy_root / "cost_ledger.jsonl").exists()


def test_strict_discovery_rejects_sibling_that_appears_after_lock_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPR_COST_DATA_DIR", raising=False)
    fake_home = tmp_path / "home"
    legacy_root = tmp_path / "checkout" / "data" / "costs"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(ledger_module, "_source_checkout_cost_data_dir", lambda: legacy_root)
    ledger = CostLedger()

    @contextmanager
    def primary_lock(_path: Path, *, deadline: float | None = None):
        del deadline
        legacy_root.mkdir(parents=True)
        (legacy_root / "cost_ledger.jsonl").write_text("", encoding="utf-8")
        yield

    monkeypatch.setattr(ledger, "_ledger_file_lock", primary_lock)
    with pytest.raises(CostLedgerReadError, match="before its lock"):
        ledger.with_locked_accounting_events(list)


def test_strict_accounting_rejects_conflicting_cross_root_idempotency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPR_COST_DATA_DIR", raising=False)
    fake_home = tmp_path / "home"
    legacy_root = tmp_path / "checkout" / "data" / "costs"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(ledger_module, "_source_checkout_cost_data_dir", lambda: legacy_root)

    CostLedger(ledger_path=legacy_root / "cost_ledger.jsonl").record_event(
        operation="research_completion",
        provider="openai",
        cost_usd=0.75,
        idempotency_key="cross-root-conflict",
    )
    CostLedger(ledger_path=fake_home / ".deepr" / "costs" / "cost_ledger.jsonl").record_event(
        operation="research_completion",
        provider="openai",
        cost_usd=0.80,
        idempotency_key="cross-root-conflict",
    )

    with pytest.raises(CostLedgerIdempotencyConflict, match="cross-root"):
        CostLedger().with_locked_accounting_events(list)


def test_canonical_reservations_count_legacy_source_checkout_holds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPR_COST_DATA_DIR", raising=False)
    fake_home = tmp_path / "home"
    legacy_root = tmp_path / "checkout" / "data" / "costs"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(ledger_module, "_source_checkout_cost_data_dir", lambda: legacy_root)
    from deepr.core import cost_caps as cost_caps_module

    monkeypatch.setattr(
        cost_caps_module,
        "resolve_spend_caps",
        lambda: {"per_job": 1.0, "daily": 1.0, "weekly": 1.0, "monthly": 1.0},
    )

    legacy = ResearchReservationStore(legacy_root / "research_reservations.db")
    _seed_reservation(
        legacy,
        reservation_id="legacy-hold",
        job_id="legacy-job",
        reserved_cost=0.75,
    )

    canonical = ResearchReservationStore()
    assert canonical.path == fake_home / ".deepr" / "costs" / "research_reservations.db"
    assert canonical.active_cost() == pytest.approx(0.75)
    with pytest.raises(ResearchReservationLimitExceeded, match="limit"):
        canonical.reserve(
            reservation_id="canonical-hold",
            job_id="canonical-job",
            reserved_cost=0.50,
            max_daily_cost=1.0,
            max_weekly_cost=1.0,
            max_monthly_cost=1.0,
        )


def test_long_lived_store_discovers_and_settles_late_legacy_hold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPR_COST_DATA_DIR", raising=False)
    fake_home = tmp_path / "home"
    legacy_root = tmp_path / "checkout" / "data" / "costs"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(ledger_module, "_source_checkout_cost_data_dir", lambda: legacy_root)

    canonical = ResearchReservationStore()
    legacy = ResearchReservationStore(legacy_root / "research_reservations.db")
    _seed_reservation(
        legacy,
        reservation_id="late-legacy-hold",
        job_id="late-legacy-job",
        reserved_cost=0.75,
    )

    assert canonical.active_cost() == pytest.approx(0.75)
    recorded: list[bool] = []
    assert canonical.settle("late-legacy-hold", 0.50, lambda: recorded.append(True)) == "settled"
    assert recorded == [True]
    assert legacy.state("late-legacy-hold") == "settled"


@pytest.mark.parametrize(
    ("canonical_ids", "legacy_ids", "message"),
    [
        (("shared-reservation", "canonical-job"), ("shared-reservation", "legacy-job"), "reservation identity"),
        (("canonical-reservation", "shared-job"), ("legacy-reservation", "shared-job"), "job identity"),
    ],
)
def test_cross_root_duplicate_reservation_or_job_identity_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    canonical_ids: tuple[str, str],
    legacy_ids: tuple[str, str],
    message: str,
) -> None:
    monkeypatch.delenv("DEEPR_COST_DATA_DIR", raising=False)
    fake_home = tmp_path / "home"
    legacy_root = tmp_path / "checkout" / "data" / "costs"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(ledger_module, "_source_checkout_cost_data_dir", lambda: legacy_root)

    legacy = ResearchReservationStore(legacy_root / "research_reservations.db")
    canonical = ResearchReservationStore()
    _seed_reservation(
        canonical,
        reservation_id=canonical_ids[0],
        job_id=canonical_ids[1],
        reserved_cost=0.50,
    )
    _seed_reservation(
        legacy,
        reservation_id=legacy_ids[0],
        job_id=legacy_ids[1],
        reserved_cost=0.75,
    )

    with pytest.raises(ResearchReservationStoreError, match=message):
        canonical.exposure_snapshot()


def test_reservation_bound_completion_does_not_close_another_hold() -> None:
    store = ResearchReservationStore()
    _seed_reservation(
        store,
        reservation_id="still-active-reservation",
        job_id="shared-completion-job",
        reserved_cost=0.75,
    )
    CostLedger().record_event(
        operation="research_completion",
        provider="openai",
        cost_usd=0.50,
        idempotency_key="job:shared-completion-job:completion",
        metadata={
            "cost_reservation_id": "different-reservation",
            "cost_reservation_job_id": "shared-completion-job",
        },
    )

    exposure = store.exposure_snapshot()
    assert exposure.active_cost == pytest.approx(0.75)
    assert exposure.unresolved_cost == pytest.approx(0.75)
    assert exposure.unresolved_count == 1
    assert store.state("still-active-reservation") == "active"


def test_explicit_reservation_path_stays_isolated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPR_COST_DATA_DIR", raising=False)
    legacy_root = tmp_path / "checkout" / "data" / "costs"
    monkeypatch.setattr(ledger_module, "_source_checkout_cost_data_dir", lambda: legacy_root)
    legacy = ResearchReservationStore(legacy_root / "research_reservations.db")
    _seed_reservation(
        legacy,
        reservation_id="legacy-only-hold",
        job_id="legacy-only-job",
        reserved_cost=0.75,
    )

    isolated = ResearchReservationStore(tmp_path / "isolated" / "research_reservations.db")
    assert isolated.active_cost() == 0.0
    assert isolated.state("legacy-only-hold") is None


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

    monkeypatch.setattr(budget_module, "_atomic_monthly_exposure", lambda: None)
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
