"""Canonical ledger location must be stable, and spend queries must see it all.

The default ledger path was CWD-dependent: an existing project-local ledger
changed both the write root and reservation database. The default is now the
stable home cost root. Strict reads still include the source checkout's legacy
ledger so its historical spend cannot disappear during migration.
"""

from __future__ import annotations

import json
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
from deepr.observability import cost_authority as authority_module
from deepr.observability.cost_ledger import (
    CostLedger,
    CostLedgerIdempotencyConflict,
    CostLedgerReadError,
    default_cost_data_dir,
)

_PRODUCTION_CWD_CHECKOUT_DISCOVERY = authority_module._cwd_checkout_cost_data_dir


@pytest.fixture(autouse=True)
def _isolate_checkout_cwd(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent the developer checkout from leaking into fake-home tests."""
    monkeypatch.setattr(authority_module, "_cwd_checkout_cost_data_dir", lambda: None)


def _seed_reservation(
    store: ResearchReservationStore,
    *,
    reservation_id: str,
    job_id: str,
    reserved_cost: float,
    provider_work_may_have_run: bool = True,
    provider: str | None = None,
    model: str | None = None,
    dispatch_binding_id: str | None = None,
    request_envelope_sha256: str | None = None,
) -> None:
    with closing(sqlite3.connect(store.path)) as connection, connection:
        connection.execute(
            """
            INSERT INTO research_cost_reservations
                (reservation_id, job_id, reserved_cost, state, created_at,
                 provider_work_may_have_run, provider, model,
                 dispatch_binding_id, request_envelope_sha256)
            VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?, ?)
            """,
            (
                reservation_id,
                job_id,
                reserved_cost,
                datetime.now(UTC).isoformat(),
                int(provider_work_may_have_run),
                provider,
                model,
                dispatch_binding_id,
                request_envelope_sha256,
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


def test_explicit_canonical_home_override_keeps_registered_cost_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_home = tmp_path / "home"
    canonical_root = fake_home / ".deepr" / "costs"
    legacy_root = tmp_path / "checkout" / "data" / "costs"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setenv("DEEPR_COST_DATA_DIR", str(canonical_root))
    monkeypatch.setattr(authority_module, "_source_checkout_cost_data_dir", lambda: legacy_root)
    monkeypatch.setattr(authority_module, "_cwd_checkout_cost_data_dir", lambda: None)

    CostLedger(ledger_path=legacy_root / "cost_ledger.jsonl").record_event(
        operation="research_completion",
        provider="openai",
        cost_usd=3.25,
        idempotency_key="explicit-home-legacy-ledger",
    )
    legacy = ResearchReservationStore(legacy_root / "research_reservations.db")
    _seed_reservation(
        legacy,
        reservation_id="explicit-home-legacy-hold",
        job_id="explicit-home-legacy-job",
        reserved_cost=0.75,
    )

    assert CostLedger().ledger_path == canonical_root / "cost_ledger.jsonl"
    assert CostLedger().get_total_cost() == pytest.approx(3.25)
    assert ResearchReservationStore().path == canonical_root / "research_reservations.db"
    assert ResearchReservationStore().active_cost() == pytest.approx(0.75)

    monkeypatch.setattr(authority_module, "_source_checkout_cost_data_dir", lambda: None)
    assert CostLedger().get_total_cost() == pytest.approx(3.25)
    assert ResearchReservationStore().active_cost() == pytest.approx(0.75)


def test_noncanonical_cost_override_remains_isolated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_home = tmp_path / "home"
    override = tmp_path / "override"
    legacy_root = tmp_path / "checkout" / "data" / "costs"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setenv("DEEPR_COST_DATA_DIR", str(override))
    monkeypatch.setattr(authority_module, "_source_checkout_cost_data_dir", lambda: legacy_root)
    monkeypatch.setattr(authority_module, "_cwd_checkout_cost_data_dir", lambda: None)

    CostLedger(ledger_path=legacy_root / "cost_ledger.jsonl").record_event(
        operation="research_completion",
        provider="openai",
        cost_usd=9.0,
        idempotency_key="custom-root-isolation",
    )
    legacy = ResearchReservationStore(legacy_root / "research_reservations.db")
    _seed_reservation(
        legacy,
        reservation_id="custom-root-legacy-hold",
        job_id="custom-root-legacy-job",
        reserved_cost=0.75,
    )

    assert CostLedger().ledger_path == override / "cost_ledger.jsonl"
    assert CostLedger().get_total_cost() == 0.0
    assert ResearchReservationStore().path == override / "research_reservations.db"
    assert ResearchReservationStore().active_cost() == 0.0


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
    monkeypatch.setattr(authority_module, "_source_checkout_cost_data_dir", lambda: tmp_path / "data" / "costs")

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


def test_registered_legacy_ledger_survives_installed_layout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPR_COST_DATA_DIR", raising=False)
    fake_home = tmp_path / "home"
    legacy_root = tmp_path / "checkout" / "data" / "costs"
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(authority_module, "_source_checkout_cost_data_dir", lambda: legacy_root)

    CostLedger(ledger_path=legacy_root / "cost_ledger.jsonl").record_event(
        operation="research_completion",
        provider="openai",
        cost_usd=38.52,
        idempotency_key="persistent-legacy-ledger",
    )
    source_health = CostLedger().get_health()
    assert source_health["total_cost_usd"] == pytest.approx(38.52)
    assert source_health["primary_write_path"] == str(fake_home / ".deepr" / "costs" / "cost_ledger.jsonl")
    assert source_health["accounting_complete"] is True
    assert {item["path"] for item in source_health["accounting_sources"]} == {
        str(fake_home / ".deepr" / "costs" / "cost_ledger.jsonl"),
        str(legacy_root / "cost_ledger.jsonl"),
    }

    monkeypatch.setattr(authority_module, "_source_checkout_cost_data_dir", lambda: None)
    monkeypatch.setattr(authority_module, "_cwd_checkout_cost_data_dir", lambda: None)
    monkeypatch.chdir(outside)
    assert CostLedger().get_total_cost() == pytest.approx(38.52)


def test_missing_registered_legacy_ledger_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPR_COST_DATA_DIR", raising=False)
    fake_home = tmp_path / "home"
    legacy_root = tmp_path / "checkout" / "data" / "costs"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(authority_module, "_source_checkout_cost_data_dir", lambda: legacy_root)

    legacy_path = legacy_root / "cost_ledger.jsonl"
    CostLedger(ledger_path=legacy_path).record_event(
        operation="research_completion",
        provider="openai",
        cost_usd=1.0,
        idempotency_key="missing-registered-ledger",
    )
    assert CostLedger().get_total_cost() == pytest.approx(1.0)
    legacy_path.unlink()
    monkeypatch.setattr(authority_module, "_source_checkout_cost_data_dir", lambda: None)
    monkeypatch.setattr(authority_module, "_cwd_checkout_cost_data_dir", lambda: None)

    with pytest.raises(CostLedgerReadError, match="registered cost ledger is missing"):
        CostLedger().get_total_cost()
    health = CostLedger().get_health()
    assert health["accounting_complete"] is False
    assert "registered cost ledger is missing" in health["error"]


def test_truncated_registered_legacy_ledger_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPR_COST_DATA_DIR", raising=False)
    fake_home = tmp_path / "home"
    legacy_root = tmp_path / "checkout" / "data" / "costs"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(authority_module, "_source_checkout_cost_data_dir", lambda: legacy_root)
    legacy_path = legacy_root / "cost_ledger.jsonl"
    CostLedger(ledger_path=legacy_path).record_event(
        operation="research_completion",
        provider="openai",
        cost_usd=5.0,
        idempotency_key="truncated-registered-ledger",
    )
    assert CostLedger().get_total_cost() == pytest.approx(5.0)

    legacy_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(authority_module, "_source_checkout_cost_data_dir", lambda: None)

    with pytest.raises(CostLedgerReadError, match="truncated or replaced"):
        CostLedger().get_total_cost()


def test_malformed_accounting_source_registry_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPR_COST_DATA_DIR", raising=False)
    fake_home = tmp_path / "home"
    registry = fake_home / ".deepr" / "costs" / "accounting_sources.jsonl"
    registry.parent.mkdir(parents=True)
    registry.write_text('{"schema_version":1,"root":"relative"}\n', encoding="utf-8")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(authority_module, "_source_checkout_cost_data_dir", lambda: None)
    monkeypatch.setattr(authority_module, "_cwd_checkout_cost_data_dir", lambda: None)

    with pytest.raises(CostLedgerReadError, match="registry"):
        CostLedger().get_total_cost()


def test_pre_anchor_v1_registry_migrates_into_cost_state_high_water(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPR_COST_DATA_DIR", raising=False)
    fake_home = tmp_path / "home"
    canonical_root = fake_home / ".deepr" / "costs"
    legacy_root = tmp_path / "legacy" / "data" / "costs"
    CostLedger(ledger_path=legacy_root / "cost_ledger.jsonl").record_event(
        operation="research_completion",
        provider="openai",
        cost_usd=4.25,
        idempotency_key="-".join(("pre", "anchor", "v1", "ledger")),
    )
    canonical_root.mkdir(parents=True)
    registry = canonical_root / "accounting_sources.jsonl"
    registry.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "registered_at": "2026-07-29T00:00:00+00:00",
                "root": str(legacy_root.resolve()),
                "artifact": "cost_ledger.jsonl",
            },
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(authority_module, "_source_checkout_cost_data_dir", lambda: None)
    monkeypatch.setattr(authority_module, "_cwd_checkout_cost_data_dir", lambda: None)

    assert CostLedger().get_total_cost() == pytest.approx(4.25)
    state = json.loads((canonical_root / "cost_state.json").read_text(encoding="utf-8"))
    assert state["schema_version"] == 2
    assert state["registry_required"] is True
    assert state["registry_size_bytes"] == registry.stat().st_size
    assert (canonical_root / "accounting_sources.required.json").is_file()


def test_empty_accounting_source_registry_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_home = tmp_path / "home"
    canonical_root = fake_home / ".deepr" / "costs"
    registry = canonical_root / "accounting_sources.jsonl"
    registry.parent.mkdir(parents=True)
    registry.write_text("", encoding="utf-8")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setenv("DEEPR_COST_DATA_DIR", str(canonical_root))
    monkeypatch.setattr(authority_module, "_source_checkout_cost_data_dir", lambda: None)
    monkeypatch.setattr(authority_module, "_cwd_checkout_cost_data_dir", lambda: None)

    with pytest.raises(CostLedgerReadError, match="registry is empty"):
        CostLedger().get_total_cost()
    with pytest.raises(ResearchReservationStoreError, match="provenance is unavailable"):
        ResearchReservationStore().active_cost()


def test_missing_required_accounting_source_registry_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPR_COST_DATA_DIR", raising=False)
    fake_home = tmp_path / "home"
    legacy_root = tmp_path / "checkout" / "data" / "costs"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(authority_module, "_source_checkout_cost_data_dir", lambda: legacy_root)
    CostLedger(ledger_path=legacy_root / "cost_ledger.jsonl").record_event(
        operation="research_completion",
        provider="openai",
        cost_usd=1.0,
        idempotency_key="required-registry-ledger",
    )
    assert CostLedger().get_total_cost() == pytest.approx(1.0)
    registry = fake_home / ".deepr" / "costs" / "accounting_sources.jsonl"
    registry.unlink()
    monkeypatch.setattr(authority_module, "_source_checkout_cost_data_dir", lambda: None)

    with pytest.raises(CostLedgerReadError, match="required accounting source registry is missing"):
        CostLedger().get_total_cost()
    with pytest.raises(ResearchReservationStoreError, match="provenance is unavailable"):
        ResearchReservationStore().active_cost()


def test_registry_and_marker_deletion_cannot_reset_existing_cost_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPR_COST_DATA_DIR", raising=False)
    fake_home = tmp_path / "home"
    legacy_root = tmp_path / "checkout" / "data" / "costs"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(authority_module, "_source_checkout_cost_data_dir", lambda: legacy_root)
    CostLedger(ledger_path=legacy_root / "cost_ledger.jsonl").record_event(
        operation="research_completion",
        provider="openai",
        cost_usd=1.0,
        idempotency_key="double-deletion-ledger",
    )
    ledger = CostLedger()
    assert ledger.get_total_cost() == pytest.approx(1.0)
    state_id = ledger.cost_state_id
    canonical_root = fake_home / ".deepr" / "costs"
    from types import SimpleNamespace

    from deepr.core.cost_caps import SpendCapConfigurationError, read_operator_budget
    from deepr.observability import provider_account_controls

    valid_until = datetime(2099, 1, 1, tzinfo=UTC)
    budget = tmp_path / "budget.json"
    budget.write_text(
        json.dumps(
            {
                "monthly_limit": 10.0,
                "paid_api_frozen": False,
                "paid_api_authorization": {
                    "authority": "verified_by_deepr",
                    "evidence_ids": ["verified-account-control"],
                    "valid_until": valid_until.isoformat(),
                    "recovered_freeze_id": "freeze-before-delete",
                    "recovered_frozen_at": datetime(2026, 7, 29, tzinfo=UTC).isoformat(),
                    "cost_state_id": state_id,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        provider_account_controls,
        "verify_paid_api_authorization",
        lambda *_args, **_kwargs: SimpleNamespace(
            evidence_ids=("verified-account-control",),
            recovered_freeze_id="freeze-before-delete",
            valid_until=valid_until,
            providers=("openai",),
            hard_monthly_limit_usd=10.0,
        ),
    )
    assert read_operator_budget(budget, provider="openai").authorization_valid is True

    (canonical_root / "accounting_sources.jsonl").unlink()
    (canonical_root / "accounting_sources.required.json").unlink()
    monkeypatch.setattr(authority_module, "_source_checkout_cost_data_dir", lambda: None)

    with pytest.raises(CostLedgerReadError, match="required accounting source marker is missing"):
        authority_module.current_cost_state_id()
    with pytest.raises(SpendCapConfigurationError, match="cost-state identity is unavailable"):
        read_operator_budget(budget, provider="openai")
    assert json.loads((canonical_root / "cost_state.json").read_text(encoding="utf-8"))["cost_state_id"] == state_id


def test_valid_nonempty_registry_rollback_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPR_COST_DATA_DIR", raising=False)
    fake_home = tmp_path / "home"
    legacy_root = tmp_path / "checkout" / "data" / "costs"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(authority_module, "_source_checkout_cost_data_dir", lambda: legacy_root)
    legacy = CostLedger(ledger_path=legacy_root / "cost_ledger.jsonl")
    legacy.record_event(
        operation="research_completion",
        provider="openai",
        cost_usd=1.0,
        idempotency_key="registry-rollback-first",
    )
    canonical = CostLedger()
    assert canonical.get_total_cost() == pytest.approx(1.0)
    registry = fake_home / ".deepr" / "costs" / "accounting_sources.jsonl"
    earlier_registry = registry.read_bytes()

    legacy.record_event(
        operation="research_completion",
        provider="openai",
        cost_usd=2.0,
        idempotency_key="registry-rollback-second",
    )
    assert canonical.get_total_cost() == pytest.approx(3.0)
    assert len(registry.read_bytes()) > len(earlier_registry)
    registry.write_bytes(earlier_registry)
    monkeypatch.setattr(authority_module, "_source_checkout_cost_data_dir", lambda: None)

    with pytest.raises(CostLedgerReadError, match="registry was truncated or replaced"):
        CostLedger().get_total_cost()


def test_duplicate_registry_keys_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPR_COST_DATA_DIR", raising=False)
    fake_home = tmp_path / "home"
    registry = fake_home / ".deepr" / "costs" / "accounting_sources.jsonl"
    registry.parent.mkdir(parents=True)
    registry.write_text(
        '{"schema_version":1,"registered_at":"2026-07-29T00:00:00+00:00",'
        f'"root":"{tmp_path.as_posix()}","artifact":"cost_ledger.jsonl",'
        '"artifact":"research_reservations.db"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(authority_module, "_source_checkout_cost_data_dir", lambda: None)

    with pytest.raises(CostLedgerReadError, match="registry is unreadable"):
        CostLedger().get_total_cost()


def test_installed_layout_registers_validated_checkout_from_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPR_COST_DATA_DIR", raising=False)
    fake_home = tmp_path / "home"
    checkout = tmp_path / "checkout"
    nested = checkout / ".agent" / "smoke"
    nested.mkdir(parents=True)
    (checkout / "src" / "deepr").mkdir(parents=True)
    (checkout / "pyproject.toml").write_text('[project]\nname = "deepr-research"\n', encoding="utf-8")
    legacy_root = checkout / "data" / "costs"
    CostLedger(ledger_path=legacy_root / "cost_ledger.jsonl").record_event(
        operation="research_completion",
        provider="openai",
        cost_usd=2.5,
        idempotency_key="wheel-cwd-ledger",
    )
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(authority_module, "_source_checkout_cost_data_dir", lambda: None)
    monkeypatch.setattr(authority_module, "_cwd_checkout_cost_data_dir", _PRODUCTION_CWD_CHECKOUT_DISCOVERY)
    monkeypatch.chdir(nested)

    assert CostLedger().get_total_cost() == pytest.approx(2.5)
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.chdir(outside)
    assert CostLedger().get_total_cost() == pytest.approx(2.5)


def test_empty_checkout_discovery_finds_late_cost_artifacts_outside_checkout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPR_COST_DATA_DIR", raising=False)
    fake_home = tmp_path / "home"
    checkout = tmp_path / "checkout"
    checkout.joinpath("src", "deepr").mkdir(parents=True)
    checkout.joinpath("pyproject.toml").write_text(
        '[project]\nname = "deepr-research"\n',
        encoding="utf-8",
    )
    legacy_root = checkout / "data" / "costs"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(authority_module, "_source_checkout_cost_data_dir", lambda: None)
    monkeypatch.setattr(authority_module, "_cwd_checkout_cost_data_dir", _PRODUCTION_CWD_CHECKOUT_DISCOVERY)
    monkeypatch.chdir(checkout)
    assert not legacy_root.exists()
    assert CostLedger().get_total_cost() == 0.0

    outside = tmp_path / "outside"
    outside.mkdir(exist_ok=True)
    monkeypatch.chdir(outside)
    CostLedger(ledger_path=legacy_root / "cost_ledger.jsonl").record_event(
        operation="research_completion",
        provider="openai",
        cost_usd=3.5,
        idempotency_key="late-checkout-ledger",
    )
    legacy_store = ResearchReservationStore(legacy_root / "research_reservations.db")
    _seed_reservation(
        legacy_store,
        reservation_id="late-checkout-reservation",
        job_id="late-checkout-job",
        reserved_cost=1.25,
    )

    assert CostLedger().get_total_cost() == pytest.approx(3.5)
    assert ResearchReservationStore().active_cost() == pytest.approx(1.25)


def test_source_and_validated_cwd_checkouts_are_both_accounting_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPR_COST_DATA_DIR", raising=False)
    fake_home = tmp_path / "home"
    source_root = tmp_path / "source" / "data" / "costs"
    cwd_checkout = tmp_path / "cwd-checkout"
    nested = cwd_checkout / "work"
    nested.mkdir(parents=True)
    cwd_checkout.joinpath("src", "deepr").mkdir(parents=True)
    cwd_checkout.joinpath("pyproject.toml").write_text(
        '[project]\nname = "deepr-research"\n',
        encoding="utf-8",
    )
    cwd_root = cwd_checkout / "data" / "costs"
    CostLedger(ledger_path=source_root / "cost_ledger.jsonl").record_event(
        operation="research_completion",
        provider="openai",
        cost_usd=1.0,
        idempotency_key="source-checkout-ledger",
    )
    CostLedger(ledger_path=cwd_root / "cost_ledger.jsonl").record_event(
        operation="research_completion",
        provider="openai",
        cost_usd=2.0,
        idempotency_key="cwd-checkout-ledger",
    )
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(authority_module, "_source_checkout_cost_data_dir", lambda: source_root)
    monkeypatch.setattr(authority_module, "_cwd_checkout_cost_data_dir", _PRODUCTION_CWD_CHECKOUT_DISCOVERY)
    monkeypatch.chdir(nested)

    assert CostLedger().get_total_cost() == pytest.approx(3.0)


def test_installed_layout_ignores_unvalidated_cwd_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPR_COST_DATA_DIR", raising=False)
    fake_home = tmp_path / "home"
    arbitrary = tmp_path / "arbitrary"
    legacy_root = arbitrary / "data" / "costs"
    CostLedger(ledger_path=legacy_root / "cost_ledger.jsonl").record_event(
        operation="research_completion",
        provider="openai",
        cost_usd=4.0,
        idempotency_key="unvalidated-cwd-ledger",
    )
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(authority_module, "_source_checkout_cost_data_dir", lambda: None)
    monkeypatch.setattr(authority_module, "_cwd_checkout_cost_data_dir", _PRODUCTION_CWD_CHECKOUT_DISCOVERY)
    monkeypatch.chdir(arbitrary)

    assert CostLedger().get_total_cost() == 0.0


def test_strict_accounting_rejects_malformed_sibling_ledger(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPR_COST_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    fake_home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(authority_module, "_source_checkout_cost_data_dir", lambda: tmp_path / "data" / "costs")

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
    monkeypatch.setattr(authority_module, "_source_checkout_cost_data_dir", lambda: legacy_root)

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
    monkeypatch.setattr(authority_module, "_source_checkout_cost_data_dir", lambda: legacy_root)

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
    monkeypatch.setattr(authority_module, "_source_checkout_cost_data_dir", lambda: legacy_root)

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
    monkeypatch.setattr(authority_module, "_source_checkout_cost_data_dir", lambda: legacy_root)
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
    monkeypatch.setattr(authority_module, "_source_checkout_cost_data_dir", lambda: legacy_root)

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
    monkeypatch.setattr(authority_module, "_source_checkout_cost_data_dir", lambda: legacy_root)
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


def test_registered_legacy_reservation_survives_installed_layout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPR_COST_DATA_DIR", raising=False)
    fake_home = tmp_path / "home"
    legacy_root = tmp_path / "checkout" / "data" / "costs"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(authority_module, "_source_checkout_cost_data_dir", lambda: legacy_root)
    legacy = ResearchReservationStore(legacy_root / "research_reservations.db")
    _seed_reservation(
        legacy,
        reservation_id="registered-legacy-hold",
        job_id="registered-legacy-job",
        reserved_cost=0.75,
    )
    assert ResearchReservationStore().active_cost() == pytest.approx(0.75)

    monkeypatch.setattr(authority_module, "_source_checkout_cost_data_dir", lambda: None)
    monkeypatch.setattr(authority_module, "_cwd_checkout_cost_data_dir", lambda: None)
    assert ResearchReservationStore().active_cost() == pytest.approx(0.75)

    legacy.path.unlink()
    with pytest.raises(ResearchReservationStoreError, match="registered reservation state is missing"):
        ResearchReservationStore().active_cost()


def test_replaced_registered_reservation_database_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPR_COST_DATA_DIR", raising=False)
    fake_home = tmp_path / "home"
    legacy_root = tmp_path / "checkout" / "data" / "costs"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(authority_module, "_source_checkout_cost_data_dir", lambda: legacy_root)
    legacy = ResearchReservationStore(legacy_root / "research_reservations.db")
    _seed_reservation(
        legacy,
        reservation_id="replace-legacy-hold",
        job_id="replace-legacy-job",
        reserved_cost=0.75,
    )
    assert ResearchReservationStore().active_cost() == pytest.approx(0.75)

    legacy.path.unlink()
    ResearchReservationStore(legacy.path)
    monkeypatch.setattr(authority_module, "_source_checkout_cost_data_dir", lambda: None)

    with pytest.raises(ResearchReservationStoreError, match="truncated or replaced"):
        ResearchReservationStore().active_cost()


def test_long_lived_store_discovers_and_settles_late_legacy_hold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPR_COST_DATA_DIR", raising=False)
    fake_home = tmp_path / "home"
    legacy_root = tmp_path / "checkout" / "data" / "costs"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(authority_module, "_source_checkout_cost_data_dir", lambda: legacy_root)

    canonical = ResearchReservationStore()
    legacy = ResearchReservationStore(legacy_root / "research_reservations.db")
    _seed_reservation(
        legacy,
        reservation_id="late-legacy-hold",
        job_id="late-legacy-job",
        reserved_cost=0.75,
        provider="openai",
        model="gpt-5-mini",
        dispatch_binding_id="a" * 64,
        request_envelope_sha256="b" * 64,
    )

    assert canonical.active_cost() == pytest.approx(0.75)
    recorded: list[bool] = []
    assert (
        canonical.settle(
            "late-legacy-hold",
            0.50,
            lambda: recorded.append(True),
            job_id="late-legacy-job",
            reserved_cost=0.75,
            provider="openai",
            model="gpt-5-mini",
            dispatch_binding_id="a" * 64,
            request_envelope_sha256="b" * 64,
        )
        == "settled"
    )
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
    monkeypatch.setattr(authority_module, "_source_checkout_cost_data_dir", lambda: legacy_root)

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
    fake_home = tmp_path / "home"
    legacy_root = tmp_path / "checkout" / "data" / "costs"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(authority_module, "_source_checkout_cost_data_dir", lambda: legacy_root)
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
