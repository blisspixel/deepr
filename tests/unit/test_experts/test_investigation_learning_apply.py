from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

from deepr.experts.investigation.learning_apply import (
    _is_producer_empty_no_op,
    apply_investigation_learning,
)


class _FakeRunStore:
    def __init__(self, root: Path, *, state: str = "completed") -> None:
        self.root = root
        self._state = state
        self.references = {
            "manifest": {"path": "artifacts/learning/manifest.json"},
            "facts": {"path": "artifacts/learning/facts.json"},
            "perspectives": {"path": "artifacts/learning/perspectives.json"},
        }

    def load_plan(self, run_id: str) -> dict:
        return {"experts": [{"name": "TKG"}]}

    def load_state(self, run_id: str) -> dict:
        return {
            "state": self._state,
            "artifacts": {
                "learning:manifest": self.references["manifest"],
                "learning:envelope:e01-tkg": self.references["facts"],
                "learning:perspective-envelope:e01-tkg": self.references["perspectives"],
            },
        }

    def read_artifact(self, run_id: str, reference: dict) -> dict:
        if reference is self.references["manifest"]:
            return {
                "entries": [
                    {
                        "expert_name": "TKG",
                        "graph_commit_envelope_artifact": self.references["facts"]["path"],
                        "perspective_graph_commit_envelope_artifact": self.references["perspectives"]["path"],
                    }
                ]
            }
        if reference is self.references["facts"]:
            return {"channel": "facts"}
        if reference is self.references["perspectives"]:
            return {"channel": "perspectives"}
        raise AssertionError("unexpected artifact reference")

    def run_dir(self, run_id: str) -> Path:
        return self.root / run_id


def test_learning_apply_blocks_incomplete_investigation(tmp_path) -> None:
    result = apply_investigation_learning(
        "inv_fixture",
        dry_run=False,
        store=_FakeRunStore(tmp_path, state="paused"),
    )

    assert result["summary"]["status"] == "blocked"
    assert result["summary"]["failure_reasons"] == ["investigation_run_not_completed"]


def test_only_producer_blocked_or_empty_envelopes_are_no_ops() -> None:
    failures = ["empty_operations", "envelope_not_ready_for_commit"]

    assert _is_producer_empty_no_op({"summary": {"status": "blocked"}, "operations": []}, failures)
    assert _is_producer_empty_no_op({"summary": {"status": "empty"}, "operations": []}, failures)
    assert not _is_producer_empty_no_op({"summary": {"status": "ready_for_commit"}, "operations": []}, failures)
    assert not _is_producer_empty_no_op(
        {"summary": {"status": "blocked"}, "operations": []},
        [*failures, "unsupported_envelope_kind"],
    )


def test_learning_apply_preflights_both_channels_before_writing(monkeypatch, tmp_path) -> None:
    calls: list[tuple[str, bool]] = []
    saved: list[str] = []
    freshness: list[str] = []
    profile = SimpleNamespace(name="TKG")

    class _Profiles:
        def load(self, name: str):
            return profile

        def find_existing_dir(self, name: str):
            return tmp_path / "experts" / "tkg"

        def save(self, value) -> None:
            saved.append(value.name)

    @contextmanager
    def _lock(name: str, verb: str):
        yield True

    def _apply(envelope, store, *, gap_tracker, dry_run):
        channel = envelope["channel"]
        calls.append((channel, dry_run))
        return {
            "contract": {"writes_graph": not dry_run},
            "summary": {
                "status": "dry_run" if dry_run else "applied",
                "planned_write_count": 1 if dry_run else 0,
                "applied_write_count": 0 if dry_run else 1,
                "already_applied_count": 0,
                "failure_reasons": [],
            },
        }

    monkeypatch.setattr("deepr.experts.investigation.learning_apply.ExpertStore", _Profiles)
    monkeypatch.setattr("deepr.experts.investigation.learning_apply.BeliefStore", lambda name: object())
    monkeypatch.setattr("deepr.experts.investigation.learning_apply.MetaCognitionTracker", lambda name: object())
    monkeypatch.setattr("deepr.experts.investigation.learning_apply.expert_verb_lock", _lock)
    monkeypatch.setattr(
        "deepr.experts.investigation.learning_apply.verify_graph_commit_provenance",
        lambda *args, **kwargs: SimpleNamespace(valid=True, failure_reasons=()),
    )
    monkeypatch.setattr("deepr.experts.investigation.learning_apply.apply_graph_commit_envelope", _apply)
    monkeypatch.setattr(
        "deepr.experts.investigation.learning_apply.advance_knowledge_freshness",
        lambda value, observed_at: freshness.append(value.name),
    )

    result = apply_investigation_learning(
        "inv_fixture",
        dry_run=False,
        store=_FakeRunStore(tmp_path),
    )

    assert calls == [
        ("facts", True),
        ("perspectives", True),
        ("facts", False),
        ("perspectives", False),
    ]
    assert result["summary"]["status"] == "applied"
    assert result["summary"]["planned_write_count"] == 2
    assert result["summary"]["applied_write_count"] == 2
    assert result["contract"]["human_reviewed"] is False
    assert result["contract"]["perspective_truth_or_novelty_verified"] is False
    assert freshness == ["TKG"]
    assert saved == ["TKG"]


def test_learning_apply_treats_producer_blocked_empty_channel_as_no_op(monkeypatch, tmp_path) -> None:
    calls: list[tuple[str, bool]] = []
    profile = SimpleNamespace(name="TKG")

    class _Profiles:
        def load(self, name: str):
            return profile

        def find_existing_dir(self, name: str):
            return tmp_path / "experts" / "tkg"

        def save(self, value) -> None:
            pass

    @contextmanager
    def _lock(name: str, verb: str):
        yield True

    def _apply(envelope, store, *, gap_tracker, dry_run):
        channel = envelope["channel"]
        calls.append((channel, dry_run))
        if channel == "facts":
            return {
                "contract": {"read_only": True, "writes_graph": False, "writes_expert_state": False},
                "summary": {
                    "status": "blocked",
                    "dry_run": True,
                    "planned_write_count": 0,
                    "applied_write_count": 0,
                    "already_applied_count": 0,
                    "failure_reasons": ["empty_operations", "envelope_not_ready_for_commit"],
                },
            }
        return {
            "contract": {
                "read_only": dry_run,
                "writes_graph": not dry_run,
                "writes_expert_state": not dry_run,
            },
            "summary": {
                "status": "dry_run" if dry_run else "applied",
                "dry_run": dry_run,
                "planned_write_count": 1 if dry_run else 0,
                "applied_write_count": 0 if dry_run else 1,
                "already_applied_count": 0,
                "failure_reasons": [],
            },
        }

    class _Store(_FakeRunStore):
        def read_artifact(self, run_id: str, reference: dict) -> dict:
            if reference is self.references["facts"]:
                return {"channel": "facts", "summary": {"status": "blocked"}, "operations": []}
            if reference is self.references["perspectives"]:
                return {
                    "channel": "perspectives",
                    "summary": {"status": "ready_for_commit"},
                    "operations": [{"operation": "promote_hypothesis"}],
                }
            return super().read_artifact(run_id, reference)

    monkeypatch.setattr("deepr.experts.investigation.learning_apply.ExpertStore", _Profiles)
    monkeypatch.setattr("deepr.experts.investigation.learning_apply.BeliefStore", lambda name: object())
    monkeypatch.setattr("deepr.experts.investigation.learning_apply.MetaCognitionTracker", lambda name: object())
    monkeypatch.setattr("deepr.experts.investigation.learning_apply.expert_verb_lock", _lock)
    monkeypatch.setattr(
        "deepr.experts.investigation.learning_apply.verify_graph_commit_provenance",
        lambda *args, **kwargs: SimpleNamespace(valid=True, failure_reasons=()),
    )
    monkeypatch.setattr("deepr.experts.investigation.learning_apply.apply_graph_commit_envelope", _apply)

    result = apply_investigation_learning("inv_fixture", dry_run=False, store=_Store(tmp_path))

    assert calls == [("facts", True), ("perspectives", True), ("perspectives", False)]
    assert result["summary"]["status"] == "applied"
    assert result["summary"]["planned_write_count"] == 1
    assert result["summary"]["applied_write_count"] == 1
    assert result["summary"]["no_op_envelope_count"] == 1
    assert result["results"][0]["result"]["summary"] == {
        "status": "empty",
        "dry_run": False,
        "planned_write_count": 0,
        "applied_write_count": 0,
        "already_applied_count": 0,
        "failure_reasons": [],
        "no_op_reasons": ["producer_blocked_or_empty"],
    }
