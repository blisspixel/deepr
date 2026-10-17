"""World-time admission stays explicit, and inspection does not write."""

from datetime import UTC, datetime, timedelta

import pytest
from click.testing import CliRunner

from deepr.cli.commands.semantic.expert_currency import affirm_claim_cmd, close_claim_cmd, currency
from deepr.experts.beliefs import Belief, BeliefStore
from deepr.experts.currency_inspection import inspect_currency
from deepr.experts.world_validity import (
    WorldValidityError,
    affirm_in_force,
    close_claim,
    live_status,
    project_world_validity,
    status_at,
)


def _store(tmp_path) -> BeliefStore:
    return BeliefStore("Currency Expert", storage_dir=tmp_path / "beliefs")


def _put(store: BeliefStore, claim: str, **kwargs: object) -> Belief:
    fields: dict[str, object] = {"confidence": 0.8, "domain": "test"}
    fields.update(kwargs)
    belief = Belief(claim=claim, **fields)  # type: ignore[arg-type]
    store.beliefs[belief.id] = belief
    store._index_belief(belief)
    return belief


def test_live_belief_without_a_mark_is_unknown(tmp_path) -> None:
    store = _store(tmp_path)
    belief = _put(store, "The manual says the default timeout is 30 seconds.")
    assert live_status(belief) == "unknown"
    projected = project_world_validity(store)
    assert projected["missing_end_means"] == "unknown"
    assert projected["live_counts"]["unknown"] == 1
    assert projected["closed_ends"] == []
    assert projected["contradictions_auto_resolved"] is False


def test_archive_stale_does_not_invent_a_world_end(tmp_path) -> None:
    store = _store(tmp_path)
    old = datetime.now(UTC) - timedelta(days=120)
    belief = _put(
        store,
        "An unused tertiary note.",
        confidence=0.3,
        created_at=old,
        updated_at=old,
    )
    changes = store.archive_stale()
    assert len(changes) == 1
    assert changes[0].invalidated_at is None
    assert belief.id not in store.beliefs
    reloaded = BeliefStore("Currency Expert", storage_dir=store.storage_dir, read_only=True)
    projected = project_world_validity(reloaded)
    assert projected["closed_ends"] == []
    assert len(projected["store_retirements_without_world_end"]) == 1


def test_close_claim_records_the_end_and_keeps_the_snapshot(tmp_path) -> None:
    store = _store(tmp_path)
    belief = _put(store, "Package 1.2 is the supported release.")
    ended = datetime(2026, 10, 1, tzinfo=UTC)
    change = close_claim(
        store,
        belief.id,
        ended_at=ended,
        basis="observed",
        evidence="Vendor changelog dated 2026-10-01.",
    )
    assert change.invalidated_at == ended
    assert belief.id not in store.beliefs
    assert change.snapshot is not None
    marks = [item for item in change.snapshot["history"] if item.get("kind") == "world_time"]
    assert marks[-1]["status"] == "closed"
    assert marks[-1]["basis"] == "observed"
    reloaded = BeliefStore("Currency Expert", storage_dir=store.storage_dir, read_only=True)
    projected = project_world_validity(reloaded)
    assert projected["closed_ends"][0]["invalidated_at"] == ended.isoformat()
    assert projected["live_counts"]["live"] == 0


def test_close_claim_refuses_decay_and_a_naive_clock(tmp_path) -> None:
    store = _store(tmp_path)
    belief = _put(store, "A claim that is merely old.")
    with pytest.raises(WorldValidityError):
        close_claim(
            store,
            belief.id,
            ended_at=datetime(2026, 10, 1, tzinfo=UTC),
            basis="decay",
            evidence="confidence fell",
        )
    with pytest.raises(WorldValidityError):
        close_claim(
            store,
            belief.id,
            ended_at=datetime(2026, 10, 1),
            basis="observed",
            evidence="changelog",
        )
    assert belief.id in store.beliefs


def test_affirm_does_not_move_confidence_or_the_decay_clock(tmp_path) -> None:
    store = _store(tmp_path)
    stamped = datetime(2026, 1, 1, tzinfo=UTC)
    belief = _put(store, "The sorting contract is stable.", created_at=stamped, updated_at=stamped)
    store._save()
    started = datetime(2024, 5, 1, tzinfo=UTC)
    affirm_in_force(store, belief.id, evidence="Language reference, unchanged section.", valid_from=started)
    reloaded = BeliefStore("Currency Expert", storage_dir=store.storage_dir, read_only=True)
    restored = reloaded.beliefs[belief.id]
    assert restored.confidence == 0.8
    assert restored.updated_at == stamped
    assert live_status(restored) == "in_force"
    assert status_at(restored, datetime(2024, 1, 1, tzinfo=UTC)) == "unknown"
    assert status_at(restored, datetime(2025, 1, 1, tzinfo=UTC)) == "in_force"


def test_closed_interval_without_a_start_stays_unknown_before_the_end() -> None:
    belief = Belief(claim="The preview model is offered.", confidence=0.5, domain="test")
    belief.history.append(
        {
            "kind": "world_time",
            "status": "closed",
            "basis": "observed",
            "invalidated_at": "2026-10-23T00:00:00+00:00",
            "valid_from": None,
            "evidence": "Shutdown notice.",
        }
    )
    assert status_at(belief, datetime(2026, 10, 1, tzinfo=UTC)) == "unknown"
    assert status_at(belief, datetime(2026, 10, 23, tzinfo=UTC)) == "closed"


def test_inspection_does_not_change_canonical_bytes(tmp_path) -> None:
    store = _store(tmp_path)
    _put(store, "Retained note.")
    store._save()
    packet = inspect_currency(tmp_path, "Currency Expert", question="What changed?")
    assert packet["files_unchanged"] is True
    assert packet["live_check"] == "not_examined"
    assert packet["further_research"] == "not_judged"
    assert packet["canonical_mutation"] is False
    assert packet["world_validity"]["live_counts"]["unknown"] == 1
    assert packet["positions"]["world_time_recorded"] is False
    again = inspect_currency(tmp_path, "Currency Expert")
    assert again["file_sha256"] == packet["file_sha256"]


def test_open_contradictions_are_listed_and_not_resolved(tmp_path) -> None:
    store = _store(tmp_path)
    left = _put(store, "The feature is on by default.")
    right = _put(store, "The feature is off by default.")
    left.add_contradiction(right.id)
    right.add_contradiction(left.id)
    projected = project_world_validity(store)
    assert projected["open_contradictions"] == [{"belief_ids": sorted([left.id, right.id])}]


def test_currency_command_is_read_only(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store(tmp_path)
    _put(store, "Command fixture.")
    store._save()
    monkeypatch.setattr(
        "deepr.cli.commands.semantic.expert_currency._resolve_expert",
        lambda _name: ("Currency Expert", tmp_path),
    )
    result = CliRunner().invoke(currency, ["Currency Expert", "--json"])
    assert result.exit_code == 0, result.output
    assert '"canonical_mutation": false' in result.output
    assert '"files_unchanged": true' in result.output


def test_affirm_refuses_a_closed_mark_left_on_a_live_belief(tmp_path) -> None:
    store = _store(tmp_path)
    belief = _put(store, "A closed mark is still sitting on the live row.")
    belief.history.append(
        {
            "kind": "world_time",
            "status": "closed",
            "basis": "observed",
            "invalidated_at": "2026-10-01T00:00:00+00:00",
            "evidence": "Shutdown notice.",
        }
    )
    with pytest.raises(WorldValidityError):
        affirm_in_force(store, belief.id, evidence="manual section")
    assert belief.confidence == 0.8
    assert live_status(belief) == "closed_mark_on_live_belief"


def test_currency_human_output_names_a_live_closed_mark(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store(tmp_path)
    belief = _put(store, "Closed in history and still listed.")
    belief.history.append(
        {
            "kind": "world_time",
            "status": "closed",
            "basis": "observed",
            "invalidated_at": "2026-10-01T00:00:00+00:00",
            "evidence": "Shutdown notice.",
        }
    )
    store._save()
    monkeypatch.setattr(
        "deepr.cli.commands.semantic.expert_currency._resolve_expert",
        lambda _name: ("Currency Expert", tmp_path),
    )
    result = CliRunner().invoke(currency, ["Currency Expert"])
    assert result.exit_code == 0, result.output
    assert "Closed marks still on live beliefs" in result.output
    assert "Those rows are defects, not current claims." in result.output


def test_write_commands_with_yes_admit_world_time(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store(tmp_path)
    keep = _put(store, "The sorting contract is stable.")
    drop = _put(store, "The preview identifier remains selectable.")
    store._save()
    monkeypatch.setattr(
        "deepr.cli.commands.semantic.expert_currency._resolve_expert",
        lambda _name: ("Currency Expert", tmp_path),
    )
    affirmed = CliRunner().invoke(
        affirm_claim_cmd,
        [
            "Currency Expert",
            "--belief-id",
            keep.id,
            "--evidence",
            "Language reference, unchanged section.",
            "--valid-from",
            "2024-05-01T00:00:00+00:00",
            "--yes",
        ],
    )
    closed = CliRunner().invoke(
        close_claim_cmd,
        [
            "Currency Expert",
            "--belief-id",
            drop.id,
            "--ended-at",
            "2026-10-23T00:00:00+00:00",
            "--basis",
            "source_resolved",
            "--evidence",
            "Vendor shutdown notice.",
            "--yes",
        ],
    )
    assert affirmed.exit_code == 0, affirmed.output
    assert closed.exit_code == 0, closed.output
    reloaded = BeliefStore("Currency Expert", storage_dir=store.storage_dir, read_only=True)
    restored = reloaded.beliefs[keep.id]
    assert live_status(restored) == "in_force"
    assert restored.confidence == 0.8
    assert drop.id not in reloaded.beliefs
    projected = project_world_validity(reloaded)
    assert projected["closed_ends"][0]["reason"] == "world_end:source_resolved"
    assert projected["live_counts"]["in_force"] == 1


def test_write_commands_refuse_without_yes(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store(tmp_path)
    belief = _put(store, "Do not close me by accident.")
    store._save()
    monkeypatch.setattr(
        "deepr.cli.commands.semantic.expert_currency._resolve_expert",
        lambda _name: ("Currency Expert", tmp_path),
    )
    closed = CliRunner().invoke(
        close_claim_cmd,
        [
            "Currency Expert",
            "--belief-id",
            belief.id,
            "--ended-at",
            "2026-10-01T00:00:00+00:00",
            "--basis",
            "observed",
            "--evidence",
            "changelog",
        ],
    )
    affirmed = CliRunner().invoke(
        affirm_claim_cmd,
        ["Currency Expert", "--belief-id", belief.id, "--evidence", "manual"],
    )
    assert closed.exit_code != 0
    assert affirmed.exit_code != 0
    reloaded = BeliefStore("Currency Expert", storage_dir=store.storage_dir, read_only=True)
    assert belief.id in reloaded.beliefs
    assert live_status(reloaded.beliefs[belief.id]) == "unknown"
