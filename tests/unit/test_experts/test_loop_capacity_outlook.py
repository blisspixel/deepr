"""Tests for the non-probing loop capacity outlook."""

from __future__ import annotations

from types import SimpleNamespace

import deepr.backends.admission as admission_mod
from deepr.backends.admission import TASK_CLASS_ABSORB, TASK_CLASS_GAP_FILL, TASK_CLASS_REFLECT, TASK_CLASS_SYNC
from deepr.experts.loop_capacity_outlook import LOOP_TASK_CLASSES, build_capacity_outlook


def _fake(model: str, task_class: str) -> SimpleNamespace:
    # build_capacity_outlook reads only .model and .task_class off each admission.
    return SimpleNamespace(model=model, task_class=task_class)


def _patch_active(monkeypatch, admissions: list[SimpleNamespace]) -> None:
    monkeypatch.setattr(admission_mod, "list_active", lambda *, now=None, path=None: list(admissions))


def test_empty_ledger_has_no_admitted_cheap_capacity(monkeypatch):
    _patch_active(monkeypatch, [])

    outlook = build_capacity_outlook()

    assert outlook["read_only"] is True
    assert outlook["probe_free"] is True
    assert outlook["any_cheap_capacity_admitted"] is False
    # Every maintenance task class is always reported, even with no admission.
    assert set(outlook["task_classes"]) == set(LOOP_TASK_CLASSES)
    for entry in outlook["task_classes"].values():
        assert entry == {
            "local_capacity_admitted": False,
            "plan_capacity_admitted": False,
            "admitted_local_models": [],
            "admitted_plan_backends": [],
        }


def test_local_admission_marks_local_capacity(monkeypatch):
    _patch_active(monkeypatch, [_fake("qwen-local", TASK_CLASS_SYNC), _fake("qwen-local", TASK_CLASS_ABSORB)])

    outlook = build_capacity_outlook()

    assert outlook["any_cheap_capacity_admitted"] is True
    sync = outlook["task_classes"][TASK_CLASS_SYNC]
    assert sync["local_capacity_admitted"] is True
    assert sync["plan_capacity_admitted"] is False
    assert sync["admitted_local_models"] == ["qwen-local"]
    # Task classes with no admission remain explicit about missing cheap capacity.
    assert outlook["task_classes"][TASK_CLASS_GAP_FILL]["local_capacity_admitted"] is False
    assert outlook["task_classes"][TASK_CLASS_REFLECT]["local_capacity_admitted"] is False


def test_plan_admission_is_separated_by_prefix(monkeypatch):
    # Plan admissions live in the same ledger with a "plan:" model prefix.
    _patch_active(monkeypatch, [_fake("plan:codex", TASK_CLASS_ABSORB)])

    outlook = build_capacity_outlook()

    absorb = outlook["task_classes"][TASK_CLASS_ABSORB]
    assert absorb["plan_capacity_admitted"] is True
    assert absorb["local_capacity_admitted"] is False
    # The "plan:" prefix is stripped to the bare backend id.
    assert absorb["admitted_plan_backends"] == ["codex"]
    assert absorb["admitted_local_models"] == []
    assert outlook["any_cheap_capacity_admitted"] is True


def test_local_and_plan_coexist_and_dedupe_in_one_task_class(monkeypatch):
    _patch_active(
        monkeypatch,
        [
            _fake("qwen-local", TASK_CLASS_SYNC),
            _fake("plan:codex", TASK_CLASS_SYNC),
            _fake("plan:claude", TASK_CLASS_SYNC),
            _fake("plan:codex", TASK_CLASS_SYNC),  # duplicate: must collapse
        ],
    )

    sync = build_capacity_outlook()["task_classes"][TASK_CLASS_SYNC]

    assert sync["local_capacity_admitted"] is True
    assert sync["plan_capacity_admitted"] is True
    assert sync["admitted_local_models"] == ["qwen-local"]
    # Sorted and de-duplicated backend ids (codex appears once despite two entries).
    assert sync["admitted_plan_backends"] == ["claude", "codex"]


def test_note_is_honest_about_liveness(monkeypatch):
    _patch_active(monkeypatch, [])

    note = build_capacity_outlook()["note"]

    # The outlook must not overclaim: admitted != reachable now.
    assert "no" in note.lower() and "probe" in note.lower()
    assert "metered" in note.lower()
    assert "never falls through" in note
    assert "may wait, require explicit metered approval, or refuse" in note


def test_real_admission_ledger_round_trip(tmp_path):
    # Exercise the real Admission -> list_active -> outlook seam (not fakes):
    # real "plan:" prefixing, real expiry, and non-maintenance classes ignored.
    from deepr.backends.admission import record_admission

    ledger = tmp_path / "admissions.jsonl"
    record_admission("qwen-local", TASK_CLASS_SYNC, path=ledger)
    record_admission("plan:codex", TASK_CLASS_ABSORB, path=ledger)
    record_admission("qwen-local", "some_other_task", path=ledger)

    outlook = build_capacity_outlook(admissions_path=ledger)

    assert outlook["any_cheap_capacity_admitted"] is True
    sync = outlook["task_classes"][TASK_CLASS_SYNC]
    assert sync["local_capacity_admitted"] is True
    assert sync["admitted_local_models"] == ["qwen-local"]
    absorb = outlook["task_classes"][TASK_CLASS_ABSORB]
    assert absorb["plan_capacity_admitted"] is True
    assert absorb["admitted_plan_backends"] == ["codex"]
    # A non-maintenance task class in the ledger is never surfaced.
    assert "some_other_task" not in outlook["task_classes"]
