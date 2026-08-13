"""Attended spend: bounded authority for work a person is watching.

The mechanism exists because paid dispatch was unusable rather than merely
default-off - unfreezing needs provider-signed evidence no adapter produces -
and an unusable control gets routed around by exporting a key and calling the
provider outside this project's ledger entirely.

These tests hold the properties that make the middle path safe rather than
merely convenient. Every one of them is a way an attended grant could quietly
become an unattended one.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from deepr.core.attended_grant import (
    GRANT_SCHEMA_VERSION,
    MAX_GRANT_MINUTES,
    MAX_GRANT_USD,
    AttendedGrantError,
    active_grant,
    grant_file_path,
    issue_grant,
    load_grant,
    revoke_grant,
    save_grant,
)


@pytest.fixture
def grant_path(tmp_path: Path) -> Path:
    return tmp_path / "attended_grant.json"


def _issue(**kwargs):
    return issue_grant(
        **{
            "amount_usd": 2.0,
            "minutes": 30,
            "cost_state_id": "cs1",
            "settled_cost_baseline_usd": 0.0,
            **kwargs,
        }
    )


def test_default_grant_path_follows_the_canonical_cost_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    isolated_cost_state = (tmp_path / "isolated-cost-state").resolve()
    monkeypatch.setenv("DEEPR_COST_DATA_DIR", str(isolated_cost_state))

    assert grant_file_path() == isolated_cost_state / "attended_grant.json"


class TestTheCeilingRefusesRatherThanClamps:
    """A silently reduced authorization is its own kind of surprise."""

    def test_a_grant_within_the_ceiling_is_issued(self) -> None:
        assert _issue(amount_usd=2.0).amount_usd == 2.0

    def test_the_ceiling_itself_is_allowed(self) -> None:
        assert MAX_GRANT_USD == 2.0
        assert _issue(amount_usd=MAX_GRANT_USD).amount_usd == MAX_GRANT_USD

    @pytest.mark.parametrize("amount", [MAX_GRANT_USD + 0.01, 200.0, 10_000.0])
    def test_above_the_ceiling_is_refused_not_reduced(self, amount: float) -> None:
        """A mistyped 200 must be refused, not reduced."""
        with pytest.raises(AttendedGrantError, match="exceeds"):
            _issue(amount_usd=amount)

    @pytest.mark.parametrize("amount", [0.0, -1.0, 0.001])
    def test_a_grant_must_authorize_something(self, amount: float) -> None:
        with pytest.raises(AttendedGrantError):
            _issue(amount_usd=amount)

    @pytest.mark.parametrize("minutes", [0, -5, MAX_GRANT_MINUTES + 1])
    def test_the_lifetime_is_bounded_at_both_ends(self, minutes: int) -> None:
        with pytest.raises(AttendedGrantError):
            _issue(minutes=minutes)

    def test_a_grant_must_be_bound_to_a_cost_state(self) -> None:
        with pytest.raises(AttendedGrantError, match="cost state"):
            _issue(cost_state_id="")

    @pytest.mark.parametrize("baseline", [True, -0.01, float("nan"), float("inf")])
    def test_a_grant_must_have_a_valid_settled_baseline(self, baseline: float) -> None:
        with pytest.raises(AttendedGrantError, match="baseline"):
            _issue(settled_cost_baseline_usd=baseline)


class TestAGrantExpires:
    """A forgotten grant that never expires is how attended becomes unattended."""

    def test_it_authorizes_while_it_lives(self, grant_path: Path) -> None:
        save_grant(_issue(minutes=30), grant_path)
        assert active_grant(cost_state_id="cs1", path=grant_path) is not None

    def test_it_stops_authorizing_after_expiry(self, grant_path: Path) -> None:
        save_grant(_issue(minutes=30), grant_path)
        later = datetime.now(UTC) + timedelta(minutes=31)
        assert active_grant(cost_state_id="cs1", now=later, path=grant_path) is None

    def test_expiry_is_exact_rather_than_generous(self, grant_path: Path) -> None:
        save_grant(_issue(minutes=30), grant_path)
        just_after = datetime.now(UTC) + timedelta(minutes=30, seconds=1)
        assert active_grant(cost_state_id="cs1", now=just_after, path=grant_path) is None


class TestItFailsClosed:
    """Every uncertainty leaves the freeze exactly as it was."""

    def test_no_grant_authorizes_nothing(self, grant_path: Path) -> None:
        assert active_grant(cost_state_id="cs1", path=grant_path) is None

    def test_a_corrupt_grant_authorizes_nothing(self, grant_path: Path) -> None:
        grant_path.write_text("{ not json", encoding="utf-8")
        assert load_grant(grant_path) is None
        assert active_grant(cost_state_id="cs1", path=grant_path) is None

    def test_a_grant_from_another_cost_state_authorizes_nothing(self, grant_path: Path) -> None:
        """Authority must not survive the ledger being replaced beneath it."""
        save_grant(_issue(), grant_path)
        assert active_grant(cost_state_id="a-different-ledger", path=grant_path) is None

    def test_an_unknown_schema_authorizes_nothing(self, grant_path: Path) -> None:
        payload = _issue().to_dict()
        payload["schema_version"] = "deepr-attended-spend-grant-v99"
        grant_path.write_text(json.dumps(payload), encoding="utf-8")
        assert active_grant(cost_state_id="cs1", path=grant_path) is None

    def test_a_tampered_amount_of_zero_authorizes_nothing(self, grant_path: Path) -> None:
        payload = _issue().to_dict()
        payload["amount_usd"] = 0.0
        grant_path.write_text(json.dumps(payload), encoding="utf-8")
        assert active_grant(cost_state_id="cs1", path=grant_path) is None

    def test_a_missing_expiry_authorizes_nothing(self, grant_path: Path) -> None:
        payload = _issue().to_dict()
        payload["expires_at"] = ""
        grant_path.write_text(json.dumps(payload), encoding="utf-8")
        assert active_grant(cost_state_id="cs1", path=grant_path) is None


class TestRevoking:
    def test_revoking_stops_authority_immediately(self, grant_path: Path) -> None:
        save_grant(_issue(), grant_path)
        assert revoke_grant(grant_path) is True
        assert active_grant(cost_state_id="cs1", path=grant_path) is None

    def test_revoking_nothing_is_not_an_error(self, grant_path: Path) -> None:
        assert revoke_grant(grant_path) is False


class TestItSurvivesTheRoundTrip:
    def test_what_was_granted_is_what_is_read_back(self, grant_path: Path) -> None:
        grant = _issue(amount_usd=1.5, reason="validate the paid path", provider="openai")
        save_grant(grant, grant_path)
        restored = load_grant(grant_path)
        assert restored is not None
        assert restored.amount_usd == 1.5
        assert restored.reason == "validate the paid path"
        assert restored.provider == "openai"
        assert restored.settled_cost_baseline_usd == 0.0
        assert restored.schema_version == GRANT_SCHEMA_VERSION

    def test_the_grant_draws_down_from_its_starting_total(self) -> None:
        grant = _issue(amount_usd=2.0, settled_cost_baseline_usd=41.16)

        assert grant.consumed_usd(total_settled_cost_usd=41.66) == pytest.approx(0.5)
        assert grant.remaining_usd(total_settled_cost_usd=41.66, active_holds_usd=0.25) == pytest.approx(1.25)

    def test_a_ledger_total_below_the_baseline_fails_closed(self) -> None:
        grant = _issue(settled_cost_baseline_usd=41.16)

        with pytest.raises(AttendedGrantError, match="below the grant baseline"):
            grant.consumed_usd(total_settled_cost_usd=41.15)


class TestTheFailOpenHoles:
    """Five ways a grant could have authorized spend it should not have.

    Every one was a fail-open: the check existed but let the bad case through,
    which on the money path is worse than no check, because the presence of the
    check is what stops anyone looking again.
    """

    def test_a_grant_with_no_cost_state_binding_authorizes_nothing(self, grant_path: Path) -> None:
        """Empty was treated as "matches any", so stripping the binding from a
        grant file made it valid against every ledger."""
        payload = _issue().to_dict()
        payload["cost_state_id"] = ""
        grant_path.write_text(json.dumps(payload), encoding="utf-8")
        assert active_grant(cost_state_id="cs1", path=grant_path) is None

    def test_an_unknown_current_cost_state_authorizes_nothing(self, grant_path: Path) -> None:
        save_grant(_issue(), grant_path)
        assert active_grant(cost_state_id="", path=grant_path) is None

    def test_a_nan_amount_is_refused_at_issue(self) -> None:
        """NaN compares False against both < and >, so it passed the floor and
        the ceiling and would have been written as an authorized amount."""
        with pytest.raises(AttendedGrantError, match="finite"):
            _issue(amount_usd=float("nan"))

    @pytest.mark.parametrize("amount", [float("inf"), float("-inf")])
    def test_an_infinite_amount_is_refused_at_issue(self, amount: float) -> None:
        with pytest.raises(AttendedGrantError, match="finite"):
            _issue(amount_usd=amount)

    def test_a_nan_amount_on_disk_authorizes_nothing(self, grant_path: Path) -> None:
        payload = _issue().to_dict()
        payload["amount_usd"] = float("nan")
        grant_path.write_text(json.dumps(payload), encoding="utf-8")
        assert active_grant(cost_state_id="cs1", path=grant_path) is None

    def test_an_amount_above_the_ceiling_on_disk_authorizes_nothing(self, grant_path: Path) -> None:
        """Editing the file must not get past what issuing refuses."""
        payload = _issue().to_dict()
        payload["amount_usd"] = 10_000.0
        grant_path.write_text(json.dumps(payload), encoding="utf-8")
        assert active_grant(cost_state_id="cs1", path=grant_path) is None

    def test_a_missing_baseline_on_disk_authorizes_nothing(self, grant_path: Path) -> None:
        payload = _issue().to_dict()
        payload.pop("settled_cost_baseline_usd")
        grant_path.write_text(json.dumps(payload), encoding="utf-8")
        assert active_grant(cost_state_id="cs1", path=grant_path) is None

    def test_an_unparseable_amount_reads_as_no_grant(self, grant_path: Path) -> None:
        """`from_dict` raised on a non-numeric amount, which would have bubbled
        out of a function documented as returning None."""
        payload = _issue().to_dict()
        payload["amount_usd"] = "two dollars"
        grant_path.write_text(json.dumps(payload), encoding="utf-8")
        assert load_grant(grant_path) is None
        assert active_grant(cost_state_id="cs1", path=grant_path) is None
