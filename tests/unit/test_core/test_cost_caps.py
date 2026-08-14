"""Unified spend caps: both env families bind, tighter wins, never fail open."""

from __future__ import annotations

import json
import os
from contextvars import Context
from pathlib import Path

import pytest

from deepr.core import cost_caps as cost_caps_module
from deepr.core.cost_caps import (
    OperatorBudget,
    SpendCapConfigurationError,
    budget_file_path,
    freeze_paid_api,
    parse_operator_budget,
    read_operator_budget_for_status,
    resolve_spend_caps,
    unattended_paid_api_scope,
)
from deepr.observability import cost_authority as authority_module

_ALL_VARS = [
    "DEEPR_MAX_COST_PER_JOB",
    "DEEPR_MAX_COST_PER_DAY",
    "DEEPR_MAX_COST_PER_WEEK",
    "DEEPR_MAX_COST_PER_MONTH",
    "DEEPR_PER_JOB_LIMIT",
    "DEEPR_DAILY_LIMIT",
    "DEEPR_WEEKLY_LIMIT",
    "DEEPR_MONTHLY_LIMIT",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch):
    for name in _ALL_VARS:
        monkeypatch.delenv(name, raising=False)


def test_documented_caps_bind(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPR_MAX_COST_PER_MONTH", "10")
    assert resolve_spend_caps()["monthly"] == 5.0


def test_tighter_bound_wins_when_both_families_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPR_MAX_COST_PER_MONTH", "10")
    monkeypatch.setenv("DEEPR_MONTHLY_LIMIT", "20")
    assert resolve_spend_caps()["monthly"] == 5.0

    monkeypatch.setenv("DEEPR_MAX_COST_PER_DAY", "50")
    monkeypatch.setenv("DEEPR_DAILY_LIMIT", "5")
    assert resolve_spend_caps()["daily"] == 5.0


def test_unreadable_wallet_file_does_not_widen_to_provider_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A $2 wallet that cannot be parsed must not restore the $5 provider cap."""
    from deepr.core.spend_wallet import wallet_file_path

    monkeypatch.setenv("DEEPR_COST_DATA_DIR", str(tmp_path / "costs"))
    path = wallet_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not-json", encoding="utf-8")

    operator = OperatorBudget(configured=True, monthly_limit=5.0, frozen=False)
    with pytest.raises(SpendCapConfigurationError, match="spend wallet"):
        cost_caps_module._with_spend_wallet(operator)


def test_malformed_values_never_fall_open(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPR_MAX_COST_PER_JOB", "not-a-number")
    with pytest.raises(SpendCapConfigurationError, match="DEEPR_MAX_COST_PER_JOB"):
        resolve_spend_caps()


def test_operator_budget_duplicate_keys_fail_closed(tmp_path: Path) -> None:
    budget = tmp_path / "budget.json"
    budget.write_text(
        '{"monthly_limit":10.0,"monthly_limit":100.0,"paid_api_frozen":false}',
        encoding="utf-8",
    )

    with pytest.raises(SpendCapConfigurationError, match="operator budget is unreadable"):
        cost_caps_module.read_operator_budget(budget, provider="openai")
    with pytest.raises(SpendCapConfigurationError, match="operator budget is unreadable"):
        freeze_paid_api("safety freeze", path=budget)


def test_validated_checkout_caps_persist_for_installed_runtime_and_cannot_widen(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_home = tmp_path / "home"
    canonical_cost_root = fake_home / ".deepr" / "costs"
    checkout = tmp_path / "checkout"
    checkout.joinpath("src", "deepr").mkdir(parents=True)
    checkout.joinpath("pyproject.toml").write_text(
        '[project]\nname = "deepr-research"\n',
        encoding="utf-8",
    )
    policy_path = checkout / ".env"
    policy_path.write_text(
        "DEEPR_MAX_COST_PER_JOB=2\nDEEPR_MAX_COST_PER_DAY=5\nDEEPR_MAX_COST_PER_MONTH=10\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setenv("DEEPR_COST_DATA_DIR", str(canonical_cost_root))
    monkeypatch.setattr(
        authority_module,
        "_source_checkout_cost_data_dir",
        lambda: checkout / "data" / "costs",
    )
    monkeypatch.setattr(authority_module, "_cwd_checkout_cost_data_dir", lambda: None)
    monkeypatch.setattr(
        cost_caps_module,
        "read_operator_budget",
        lambda *_args, **_kwargs: OperatorBudget(configured=True, monthly_limit=200.0, frozen=False),
    )

    expected = {"per_job": 2.0, "daily": 5.0, "weekly": 5.0, "monthly": 5.0}
    assert resolve_spend_caps() == expected

    monkeypatch.setattr(authority_module, "_source_checkout_cost_data_dir", lambda: None)
    assert resolve_spend_caps() == expected

    policy_path.write_text(
        "DEEPR_MAX_COST_PER_JOB=4\nDEEPR_MAX_COST_PER_DAY=8\nDEEPR_MAX_COST_PER_MONTH=20\n",
        encoding="utf-8",
    )
    with pytest.raises(SpendCapConfigurationError, match="widened a binding limit"):
        resolve_spend_caps()

    policy_path.unlink()
    with pytest.raises(SpendCapConfigurationError, match="registered spend-cap source is missing"):
        resolve_spend_caps()


def test_runtime_caps_do_not_contaminate_checkout_file_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_home = tmp_path / "home"
    canonical_cost_root = fake_home / ".deepr" / "costs"
    checkout = tmp_path / "checkout"
    checkout.joinpath("src", "deepr").mkdir(parents=True)
    checkout.joinpath("pyproject.toml").write_text(
        '[project]\nname = "deepr-research"\n',
        encoding="utf-8",
    )
    checkout.joinpath(".env").write_text(
        "DEEPR_MAX_COST_PER_JOB=2\nDEEPR_MAX_COST_PER_DAY=5\nDEEPR_MAX_COST_PER_MONTH=10\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setenv("DEEPR_COST_DATA_DIR", str(canonical_cost_root))
    monkeypatch.setenv("DEEPR_MAX_COST_PER_DAY", "2")
    monkeypatch.setenv("DEEPR_MAX_COST_PER_MONTH", "5")
    monkeypatch.setattr(
        authority_module,
        "_source_checkout_cost_data_dir",
        lambda: checkout / "data" / "costs",
    )
    monkeypatch.setattr(authority_module, "_cwd_checkout_cost_data_dir", lambda: None)
    monkeypatch.setattr(
        cost_caps_module,
        "read_operator_budget",
        lambda *_args, **_kwargs: OperatorBudget(configured=True, monthly_limit=200.0, frozen=False),
    )

    assert resolve_spend_caps() == {"per_job": 2.0, "daily": 2.0, "weekly": 5.0, "monthly": 5.0}
    registry = canonical_cost_root / "accounting_sources.jsonl"
    records = [json.loads(line) for line in registry.read_text(encoding="utf-8").splitlines()]
    spend_cap_record = next(record for record in records if record["artifact"] == "spend_caps.env")
    assert spend_cap_record["limits"] == {"daily": 5.0, "monthly": 10.0, "per_job": 2.0}

    monkeypatch.delenv("DEEPR_MAX_COST_PER_DAY")
    monkeypatch.delenv("DEEPR_MAX_COST_PER_MONTH")
    assert resolve_spend_caps() == {"per_job": 2.0, "daily": 5.0, "weekly": 5.0, "monthly": 5.0}


def test_spend_cap_registry_rollback_cannot_erase_tighter_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_home = tmp_path / "home"
    canonical_cost_root = fake_home / ".deepr" / "costs"
    checkout = tmp_path / "checkout"
    checkout.joinpath("src", "deepr").mkdir(parents=True)
    checkout.joinpath("pyproject.toml").write_text(
        '[project]\nname = "deepr-research"\n',
        encoding="utf-8",
    )
    policy_path = checkout / ".env"
    policy_path.write_text(
        "DEEPR_MAX_COST_PER_JOB=2\nDEEPR_MAX_COST_PER_DAY=5\nDEEPR_MAX_COST_PER_MONTH=10\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setenv("DEEPR_COST_DATA_DIR", str(canonical_cost_root))
    monkeypatch.setattr(
        authority_module,
        "_source_checkout_cost_data_dir",
        lambda: checkout / "data" / "costs",
    )
    monkeypatch.setattr(authority_module, "_cwd_checkout_cost_data_dir", lambda: None)
    monkeypatch.setattr(
        cost_caps_module,
        "read_operator_budget",
        lambda *_args, **_kwargs: OperatorBudget(configured=True, monthly_limit=200.0, frozen=False),
    )

    assert resolve_spend_caps()["monthly"] == 5.0
    registry = canonical_cost_root / "accounting_sources.jsonl"
    earlier_registry = registry.read_bytes()
    policy_path.write_text(
        "DEEPR_MAX_COST_PER_JOB=1\nDEEPR_MAX_COST_PER_DAY=3\nDEEPR_MAX_COST_PER_MONTH=6\n",
        encoding="utf-8",
    )
    assert resolve_spend_caps()["monthly"] == 5.0
    assert len(registry.read_bytes()) > len(earlier_registry)

    registry.write_bytes(earlier_registry)
    policy_path.write_text(
        "DEEPR_MAX_COST_PER_JOB=4\nDEEPR_MAX_COST_PER_DAY=8\nDEEPR_MAX_COST_PER_MONTH=20\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(authority_module, "_source_checkout_cost_data_dir", lambda: None)
    with pytest.raises(SpendCapConfigurationError, match="registry was truncated or replaced"):
        resolve_spend_caps()


def test_relative_operator_budget_path_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPR_BUDGET_FILE", "relative/budget.json")

    with pytest.raises(SpendCapConfigurationError, match="absolute path"):
        budget_file_path()


def test_relative_home_budget_path_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPR_BUDGET_FILE", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: Path("relative-home")))

    with pytest.raises(SpendCapConfigurationError, match="home path must be absolute"):
        budget_file_path()


def test_zero_is_a_real_freeze(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPR_MAX_COST_PER_DAY", "0")
    assert resolve_spend_caps() == {"per_job": 0.0, "daily": 0.0, "weekly": 5.0, "monthly": 5.0}


def test_operator_budget_is_a_binding_ceiling(tmp_path) -> None:
    path = tmp_path / "budget.json"
    active = json.loads(Path(os.environ["DEEPR_BUDGET_FILE"]).read_text(encoding="utf-8"))
    path.write_text(
        json.dumps(
            {
                "monthly_limit": 10,
                "paid_api_authorization": active["paid_api_authorization"],
            }
        ),
        encoding="utf-8",
    )
    assert resolve_spend_caps(budget_path=path) == {
        "per_job": 1.0,
        "daily": 2.0,
        "weekly": 5.0,
        "monthly": 5.0,
    }


def test_mutable_inline_authorization_alone_never_authorizes(tmp_path) -> None:
    path = tmp_path / "budget.json"
    path.write_text(
        json.dumps(
            {
                "monthly_limit": 10,
                "paid_api_authorization": {
                    "authority": "verified_by_deepr",
                    "evidence_ids": ["0" * 64],
                    "valid_until": "2099-01-01T00:00:00+00:00",
                    "recovered_freeze_id": "forged-freeze",
                    "recovered_frozen_at": "2026-07-27T00:00:00+00:00",
                    "cost_state_id": authority_module.current_cost_state_id(),
                },
            }
        ),
        encoding="utf-8",
    )

    assert resolve_spend_caps(budget_path=path)["monthly"] == 0.0


def test_paid_authority_requires_provider_binding() -> None:
    caps = Context().run(resolve_spend_caps)

    assert caps == {"per_job": 0.0, "daily": 0.0, "weekly": 0.0, "monthly": 0.0}


def test_positive_authority_is_bound_to_one_cost_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert resolve_spend_caps()["monthly"] > 0

    monkeypatch.setenv("DEEPR_COST_DATA_DIR", str(tmp_path / "different-cost-state"))

    assert resolve_spend_caps() == {"per_job": 0.0, "daily": 0.0, "weekly": 0.0, "monthly": 0.0}


def test_manual_freeze_collapses_every_window(tmp_path) -> None:
    path = tmp_path / "budget.json"
    path.write_text('{"monthly_limit": 10, "paid_api_frozen": true}', encoding="utf-8")
    assert resolve_spend_caps(budget_path=path) == {
        "per_job": 0.0,
        "daily": 0.0,
        "weekly": 0.0,
        "monthly": 0.0,
    }


def test_wallet_and_verified_provider_authority_compose_and_unattended_ignores_wallet() -> None:
    from deepr.core.spend_wallet import create_wallet, save_wallet
    from deepr.observability.cost_ledger import current_cost_state_id

    save_wallet(
        create_wallet(
            amount_usd=50.0,
            cost_state_id=current_cost_state_id(),
            settled_cost_baseline_usd=41.16,
        )
    )

    assert resolve_spend_caps() == {"per_job": 5.0, "daily": 5.0, "weekly": 5.0, "monthly": 5.0}
    with unattended_paid_api_scope():
        assert resolve_spend_caps() == {"per_job": 1.0, "daily": 2.0, "weekly": 5.0, "monthly": 5.0}


def test_unverified_provider_stays_blocked_while_status_shows_provider_neutral_wallet() -> None:
    from deepr.core.spend_wallet import create_wallet, save_wallet
    from deepr.observability.cost_ledger import current_cost_state_id

    budget = Path(os.environ["DEEPR_BUDGET_FILE"])
    budget.write_text(
        json.dumps({"monthly_limit": 0.0, "paid_api_frozen": True, "freeze_reason": "default freeze"}),
        encoding="utf-8",
    )
    save_wallet(
        create_wallet(
            amount_usd=200.0,
            cost_state_id=current_cost_state_id(),
            settled_cost_baseline_usd=0.0,
        )
    )

    assert resolve_spend_caps(provider="anthropic")["monthly"] == 0.0
    assert resolve_spend_caps(provider="openai")["monthly"] == 0.0
    assert read_operator_budget_for_status().spend_wallet_authorized_usd == 200.0
    with unattended_paid_api_scope():
        assert read_operator_budget_for_status().frozen is True


def test_explicit_environment_cap_can_narrow_wallet_and_job_authority(monkeypatch: pytest.MonkeyPatch) -> None:
    from deepr.core.spend_wallet import create_wallet, save_wallet
    from deepr.observability.cost_ledger import current_cost_state_id

    save_wallet(
        create_wallet(
            amount_usd=50.0,
            cost_state_id=current_cost_state_id(),
            settled_cost_baseline_usd=0.0,
        )
    )
    monkeypatch.setenv("DEEPR_MAX_COST_PER_JOB", "0.75")

    caps = resolve_spend_caps()
    assert caps["per_job"] == 0.75
    assert caps["per_job"] <= caps["daily"] <= caps["weekly"] <= caps["monthly"] <= 50.0


def test_wallet_policy_distinguishes_cumulative_pool_from_calendar_caps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deepr.core.cost_caps import resolve_spend_policy
    from deepr.core.spend_wallet import create_wallet, save_wallet
    from deepr.observability import cost_ledger
    from deepr.observability.cost_ledger import current_cost_state_id

    save_wallet(
        create_wallet(
            amount_usd=200.0,
            cost_state_id=current_cost_state_id(),
            settled_cost_baseline_usd=0.0,
        )
    )
    monkeypatch.setattr(cost_ledger, "well_known_spend_cap_env_paths", lambda: ())

    assert resolve_spend_policy().calendar_periods == frozenset(("daily", "weekly", "monthly"))
    monkeypatch.setenv("DEEPR_MAX_COST_PER_MONTH", "5.00")
    policy = resolve_spend_policy()
    assert policy.caps["monthly"] == 5.0
    assert policy.calendar_periods == frozenset(("daily", "weekly", "monthly"))


def test_verified_provider_hard_stop_and_wallet_both_apply() -> None:
    from deepr.core.cost_caps import resolve_spend_policy
    from deepr.core.spend_wallet import create_wallet, save_wallet
    from deepr.observability.cost_ledger import current_cost_state_id

    save_wallet(
        create_wallet(
            amount_usd=200.0,
            cost_state_id=current_cost_state_id(),
            settled_cost_baseline_usd=0.0,
        )
    )

    operator = read_operator_budget_for_status()
    assert operator.spend_wallet_authorized_usd == 200.0
    assert operator.authorization_hard_monthly_limit == 5.0
    policy = resolve_spend_policy()
    assert policy.caps["monthly"] == 5.0
    assert policy.calendar_periods == frozenset(("daily", "weekly", "monthly"))


def test_wallet_never_turns_unverified_numeric_provider_budget_into_authority() -> None:
    from deepr.core.cost_caps import read_operator_budget
    from deepr.core.spend_wallet import create_wallet, save_wallet
    from deepr.observability.cost_ledger import current_cost_state_id

    Path(os.environ["DEEPR_BUDGET_FILE"]).write_text(
        json.dumps({"monthly_limit": 50.0}),
        encoding="utf-8",
    )
    save_wallet(
        create_wallet(
            amount_usd=20.0,
            cost_state_id=current_cost_state_id(),
            settled_cost_baseline_usd=0.0,
        )
    )

    operator = read_operator_budget(provider="openai")
    assert operator.spend_wallet_authorized_usd == 20.0
    assert operator.authorization_valid is False
    assert operator.frozen is True
    assert resolve_spend_caps(provider="openai")["monthly"] == 0.0


def test_manual_freeze_after_funding_cannot_be_cleared_by_wallet_top_up() -> None:
    from deepr.core.cost_caps import freeze_paid_api
    from deepr.core.spend_wallet import add_credits, create_wallet, load_wallet, save_wallet
    from deepr.observability.cost_ledger import current_cost_state_id

    save_wallet(
        create_wallet(
            amount_usd=50.0,
            cost_state_id=current_cost_state_id(),
            settled_cost_baseline_usd=0.0,
        )
    )
    freeze_paid_api("operator stop", kind="manual")
    assert resolve_spend_caps()["monthly"] == 0.0

    wallet = load_wallet()
    assert wallet is not None
    save_wallet(add_credits(wallet, amount_usd=1.0, cost_state_id=current_cost_state_id()))
    assert resolve_spend_caps()["monthly"] == 0.0


def test_billing_divergence_freeze_cannot_be_bypassed_by_wallet_top_up() -> None:
    from deepr.core.cost_caps import freeze_paid_api
    from deepr.core.spend_wallet import add_credits, create_wallet, load_wallet, save_wallet
    from deepr.observability.cost_ledger import current_cost_state_id

    save_wallet(
        create_wallet(
            amount_usd=50.0,
            cost_state_id=current_cost_state_id(),
            settled_cost_baseline_usd=0.0,
        )
    )
    freeze_paid_api("billing does not reconcile", kind="billing_divergence")
    wallet = load_wallet()
    assert wallet is not None
    save_wallet(add_credits(wallet, amount_usd=50.0, cost_state_id=current_cost_state_id()))

    assert resolve_spend_caps() == {"per_job": 0.0, "daily": 0.0, "weekly": 0.0, "monthly": 0.0}


def test_missing_monthly_authority_is_default_off(tmp_path) -> None:
    assert resolve_spend_caps(budget_path=tmp_path / "missing.json") == {
        "per_job": 0.0,
        "daily": 0.0,
        "weekly": 0.0,
        "monthly": 0.0,
    }


def test_numeric_budget_without_account_control_evidence_is_frozen(tmp_path) -> None:
    path = tmp_path / "budget.json"
    path.write_text('{"monthly_limit": 10}', encoding="utf-8")

    operator = parse_operator_budget(json.loads(path.read_text(encoding="utf-8")))

    assert operator.frozen is True
    assert operator.freeze_kind == "account_control_unknown"
    assert resolve_spend_caps(budget_path=path)["monthly"] == 0.0


def test_expired_account_control_evidence_is_frozen(tmp_path) -> None:
    path = tmp_path / "budget.json"
    path.write_text(
        json.dumps(
            {
                "monthly_limit": 10,
                "paid_api_authorization": {
                    "authority": "verified_by_deepr",
                    "evidence_ids": ["expired-test-evidence"],
                    "valid_until": "2026-01-01T00:00:00+00:00",
                    "cost_state_id": authority_module.current_cost_state_id(),
                },
            }
        ),
        encoding="utf-8",
    )

    operator = parse_operator_budget(json.loads(path.read_text(encoding="utf-8")))

    assert operator.frozen is True
    assert operator.freeze_kind == "account_control_expired"
    assert resolve_spend_caps(budget_path=path)["monthly"] == 0.0


def test_weekly_cap_is_normalized_into_narrower_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPR_MAX_COST_PER_WEEK", "3")
    assert resolve_spend_caps() == {"per_job": 1.0, "daily": 2.0, "weekly": 3.0, "monthly": 5.0}


def test_automatic_freeze_preserves_budget_document_fields(tmp_path) -> None:
    path = tmp_path / "budget.json"
    path.write_text(
        '{"monthly_limit": 10, "monthly_spending": 3, "history": [{"job_id": "kept"}]}',
        encoding="utf-8",
    )

    operator = freeze_paid_api("reported cost divergence", path=path)

    assert operator.frozen is True
    assert operator.freeze_reason == "reported cost divergence"
    assert operator.freeze_kind == "manual"
    assert operator.freeze_id.startswith("freeze_")
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["monthly_limit"] == 10
    assert document["monthly_spending"] == 3
    assert document["history"] == [{"job_id": "kept"}]
