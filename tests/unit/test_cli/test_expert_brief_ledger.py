"""A successful brief must not hide a failed position-ledger write."""

from types import SimpleNamespace

import pytest

from deepr.cli.commands.semantic.expert_study import PositionLedgerWriteError, _record_positions


def test_record_positions_fails_when_ledger_write_fails(monkeypatch, tmp_path) -> None:
    class Ledger:
        live = []

        def to_dict(self):
            return {"threads": []}

    monkeypatch.setattr(
        "deepr.cli.commands.semantic.expert_study.canonical_position_ledger_path",
        lambda name: tmp_path / "history.json",
    )
    monkeypatch.setattr("deepr.experts.position_ledger.load_ledger", lambda *args, **kwargs: Ledger())
    monkeypatch.setattr("deepr.experts.position_ledger.record_brief", lambda *args, **kwargs: {"new": 1})

    def _raise(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("deepr.utils.atomic_io.atomic_write_json", _raise)

    with pytest.raises(PositionLedgerWriteError, match="could not record position history"):
        _record_positions("keel", SimpleNamespace(positions=[]), SimpleNamespace(outcomes=[]))
