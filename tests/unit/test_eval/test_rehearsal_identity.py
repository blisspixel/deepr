"""Rehearsal identity includes transitive code and refuses drift without side effects."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from deepr.evals import rehearsal_identity as identity


@pytest.fixture
def installation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    package = tmp_path / "src" / "deepr"
    (package / "evals").mkdir(parents=True)
    (package / "experts").mkdir()
    (package / "evals/rehearsal_identity.py").write_text("# identity fixture\n")
    (package / "experts/brief_selection.py").write_text("LIMIT = 1\n")
    (tmp_path / "uv.lock").write_text("lock fixture\n")
    (tmp_path / "pyproject.toml").write_text("metadata fixture\n")
    monkeypatch.setattr(identity, "__file__", str(package / "evals/rehearsal_identity.py"))
    monkeypatch.setattr(
        identity.metadata, "distributions", lambda: [SimpleNamespace(metadata={"Name": "fixture"}, version="1")]
    )
    monkeypatch.setattr(
        identity, "sys", SimpleNamespace(implementation=SimpleNamespace(name="cpython"), version="runtime 1")
    )
    return package


@pytest.mark.parametrize("change", ["edit", "add", "delete", "rename", "runtime", "dependency", "lock", "metadata"])
def test_resume_refuses_each_execution_change_before_writes(
    installation: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    run = tmp_path / "run"
    run.mkdir()
    saved = identity.execution_identity()
    record = run / "run.json"
    record.write_text(json.dumps({"application": {"module_sha256": {"legacy": "pin"}, "execution_identity": saved}}))
    before = record.read_bytes()
    source = installation / "experts/brief_selection.py"
    if change == "edit":
        source.write_text("LIMIT = 2\n")
    elif change == "add":
        (installation / "experts/new_dependency.py").write_text("NEW = True\n")
    elif change == "delete":
        source.unlink()
    elif change == "rename":
        source.rename(source.with_name("moved.py"))
    elif change == "runtime":
        monkeypatch.setattr(identity.sys, "version", "runtime 2")
    elif change == "dependency":
        monkeypatch.setattr(
            identity.metadata, "distributions", lambda: [SimpleNamespace(metadata={"Name": "fixture"}, version="2")]
        )
    else:
        (tmp_path / ("uv.lock" if change == "lock" else "pyproject.toml")).write_text("changed\n")
    with pytest.raises(ValueError, match="execution identity changed"):
        identity.verify_resume_identity(run, {"legacy": "pin"})
    assert record.read_bytes() == before and list(run.iterdir()) == [record]


def test_wheel_identity_has_no_checkout_and_ignores_absolute_install_path(installation: Path, tmp_path: Path) -> None:
    import shutil

    wheel = tmp_path / "wheel" / "deepr"
    shutil.copytree(installation, wheel)
    copied = tmp_path / "other" / "deepr"
    shutil.copytree(installation, copied)
    assert identity.execution_identity(wheel)["checkout_sha256"] is None
    assert identity.execution_identity(wheel) == identity.execution_identity(copied)
    before = identity.identity_sha256(identity.execution_identity(wheel))
    (wheel / "experts/brief_selection.py").write_text("LIMIT = 2\n")
    assert identity.identity_sha256(identity.execution_identity(wheel)) != before


def test_unchanged_resume_and_historical_refusal(installation: Path, tmp_path: Path) -> None:
    run = tmp_path / "run"
    run.mkdir()
    payload = identity.execution_identity()
    record = run / "run.json"
    record.write_text(json.dumps({"application": {"module_sha256": {}, "execution_identity": payload}}))
    assert identity.verify_resume_identity(run, {}) == payload
    record.write_text(json.dumps({"application": {"module_sha256": {"historical": "pin"}}}))
    before = record.read_bytes()
    with pytest.raises(ValueError, match="historical rehearsal"):
        identity.verify_resume_identity(run, {})
    assert record.read_bytes() == before


def test_unreadable_identity_and_missing_worker_receipt_cannot_pass(
    installation: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = identity.identity_sha256(identity.execution_identity())
    assert identity.execution_checks([], expected)["worker_execution_identity_matches"] is None
    assert identity.execution_checks([{"status": "completed"}], expected)["worker_execution_identity_matches"] is False
    assert (
        identity.execution_checks([{"error_type": "RehearsalIdentityError"}], expected)["execution_identity_unchanged"]
        is False
    )

    def unreadable() -> None:
        raise OSError("fixture source unavailable")

    monkeypatch.setattr(identity, "execution_identity", unreadable)
    with pytest.raises(identity.RehearsalIdentityError, match="could not be read"):
        identity.check_execution_identity(expected)
    assert identity.execution_checks([], expected)["execution_identity_unchanged"] is False
