"""Persistent metered-spend wallet safety properties."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from deepr.core.spend_wallet import (
    WALLET_SCHEMA_VERSION,
    SpendWalletError,
    active_wallet,
    add_credits,
    clear_wallet,
    create_wallet,
    load_wallet,
    save_wallet,
    wallet_file_path,
)

_COST_STATE_ID = "1" * 32


@pytest.fixture
def wallet_path(tmp_path: Path) -> Path:
    return tmp_path / "spend_wallet.json"


def _wallet(**overrides):
    values = {
        "amount_usd": 50.0,
        "cost_state_id": _COST_STATE_ID,
        "settled_cost_baseline_usd": 41.16,
    }
    values.update(overrides)
    return create_wallet(**values)


def test_default_wallet_path_follows_canonical_cost_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    isolated = (tmp_path / "isolated-cost-state").resolve()
    monkeypatch.setenv("DEEPR_COST_DATA_DIR", str(isolated))

    assert wallet_file_path() == isolated / "spend_wallet.json"


@pytest.mark.parametrize("amount", [0.01, 2.0, 50.0, 200.0, 10_000.0])
def test_operator_can_choose_positive_exact_cent_authorization(amount: float) -> None:
    assert _wallet(amount_usd=amount).authorized_usd == amount


@pytest.mark.parametrize(
    "amount",
    [True, 0.0, -1.0, 0.001, float("nan"), float("inf"), float("-inf"), "50.00"],
)
def test_invalid_credit_amount_is_refused_not_clamped(amount: object) -> None:
    with pytest.raises(SpendWalletError):
        _wallet(amount_usd=amount)


def test_top_up_is_additive_and_preserves_identity_and_baseline() -> None:
    original = _wallet(amount_usd=50.0)
    funded = add_credits(original, amount_usd=150.0, cost_state_id=_COST_STATE_ID)

    assert funded.authorized_usd == 200.0
    assert funded.wallet_id == original.wallet_id
    assert funded.settled_cost_baseline_usd == original.settled_cost_baseline_usd
    assert funded.created_at == original.created_at


def test_top_up_requires_current_cost_state() -> None:
    with pytest.raises(SpendWalletError, match="current cost state"):
        add_credits(_wallet(), amount_usd=1.0, cost_state_id="2" * 32)


def test_top_up_time_cannot_move_backward() -> None:
    now = datetime.now(UTC)
    wallet = _wallet(now=now)

    with pytest.raises(SpendWalletError, match="cannot precede"):
        add_credits(wallet, amount_usd=1.0, cost_state_id=_COST_STATE_ID, now=now - timedelta(seconds=1))


def test_all_later_settled_cost_and_active_holds_draw_down_one_pool() -> None:
    wallet = _wallet(amount_usd=50.0, settled_cost_baseline_usd=41.16)

    assert wallet.consumed_usd(total_settled_cost_usd=42.16) == pytest.approx(1.0)
    assert wallet.available_usd(total_settled_cost_usd=42.16, active_holds_usd=9.0) == pytest.approx(40.0)


def test_wallet_has_no_overdraft_or_automatic_refill() -> None:
    wallet = _wallet(amount_usd=2.0, settled_cost_baseline_usd=0.0)

    assert wallet.available_usd(total_settled_cost_usd=2.0) == 0.0
    assert wallet.available_usd(total_settled_cost_usd=3.0) == 0.0
    assert wallet.authorized_usd == 2.0


def test_ledger_rollback_below_baseline_fails_closed() -> None:
    with pytest.raises(SpendWalletError, match="below the wallet baseline"):
        _wallet().consumed_usd(total_settled_cost_usd=41.15)


def test_round_trip_preserves_exact_cents_and_metadata(wallet_path: Path) -> None:
    wallet = _wallet(amount_usd=50.29, reason="Bound one attended research campaign")
    save_wallet(wallet, wallet_path)

    restored = load_wallet(wallet_path)
    assert restored is not None
    assert restored.schema_version == WALLET_SCHEMA_VERSION
    assert restored.authorized_cents == 5029
    assert restored.authorized_usd == 50.29
    assert restored.reason == "Bound one attended research campaign"


def test_active_wallet_requires_matching_cost_state(wallet_path: Path) -> None:
    save_wallet(_wallet(), wallet_path)

    assert active_wallet(cost_state_id=_COST_STATE_ID, path=wallet_path) is not None
    assert active_wallet(cost_state_id="2" * 32, path=wallet_path) is None
    assert active_wallet(cost_state_id="", path=wallet_path) is None


@pytest.mark.parametrize(
    "raw",
    [
        "{not json",
        "[]",
        '{"schema_version": NaN}',
        '{"schema_version":"a","schema_version":"b"}',
    ],
)
def test_malformed_json_authorizes_nothing(wallet_path: Path, raw: str) -> None:
    wallet_path.write_text(raw, encoding="utf-8")

    assert load_wallet(wallet_path) is None
    assert active_wallet(cost_state_id=_COST_STATE_ID, path=wallet_path) is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "deepr-metered-spend-wallet-v99"),
        ("wallet_id", "not-hex"),
        ("cost_state_id", "not-hex"),
        ("authorized_cents", 0),
        ("authorized_cents", True),
        ("authorized_cents", "5000"),
        ("created_at", "2026-08-13T00:00:00"),
        ("updated_at", "2026-08-13T00:00:00"),
        ("settled_cost_baseline_usd", -0.01),
        ("settled_cost_baseline_usd", "41.16"),
        ("reason", 42),
    ],
)
def test_tampered_field_authorizes_nothing(wallet_path: Path, field: str, value: object) -> None:
    payload = _wallet().to_dict()
    payload[field] = value
    wallet_path.write_text(json.dumps(payload), encoding="utf-8")

    assert active_wallet(cost_state_id=_COST_STATE_ID, path=wallet_path) is None


def test_unknown_or_missing_fields_authorize_nothing(wallet_path: Path) -> None:
    payload = _wallet().to_dict()
    payload["automatic_refill"] = True
    wallet_path.write_text(json.dumps(payload), encoding="utf-8")
    assert load_wallet(wallet_path) is None

    payload = _wallet().to_dict()
    payload.pop("settled_cost_baseline_usd")
    wallet_path.write_text(json.dumps(payload), encoding="utf-8")
    assert load_wallet(wallet_path) is None


def test_update_before_creation_authorizes_nothing(wallet_path: Path) -> None:
    payload = _wallet().to_dict()
    payload["updated_at"] = (datetime.fromisoformat(payload["created_at"]) - timedelta(seconds=1)).isoformat()
    wallet_path.write_text(json.dumps(payload), encoding="utf-8")

    assert active_wallet(cost_state_id=_COST_STATE_ID, path=wallet_path) is None


def test_reason_is_bounded() -> None:
    with pytest.raises(SpendWalletError, match="at most"):
        _wallet(reason="x" * 501)


def test_clear_blocks_new_authority_without_altering_the_document_contents_first(wallet_path: Path) -> None:
    wallet = _wallet()
    save_wallet(wallet, wallet_path)
    persisted = wallet_path.read_bytes()

    assert clear_wallet(wallet_path) is True
    assert persisted
    assert active_wallet(cost_state_id=_COST_STATE_ID, path=wallet_path) is None
    assert clear_wallet(wallet_path) is False
