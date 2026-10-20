"""Historical diagnostic review retains its original identity and every verifier."""

import asyncio
import hashlib
import json
import shutil

import pytest
from click.testing import CliRunner

from deepr.cli.main import cli
from deepr.evals import correction_survival as cs
from deepr.evals.correction_survival_cases import CASES


def fingerprints(root):
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()
    }


@pytest.fixture(scope="module")
def retained(tmp_path_factory):
    root = tmp_path_factory.mktemp("historical-review") / "run"
    calls = 0

    async def completion(_prompt):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError("synthetic failure retained in the denominator")
        return cs.MOCK_ANSWER

    run = asyncio.run(cs.run_diagnostic(root, cases=CASES[:1], completion=completion, code_identity="original-build"))
    return root, run


def test_historical_review_is_pinned_read_only_and_keeps_original_identity(retained, monkeypatch):
    root, original = retained
    before = fingerprints(root)
    monkeypatch.setattr(cs, "recipe_sha256", lambda: "f" * 64)
    with pytest.raises(cs.RunNotReusableError, match="different selection or packing code"):
        cs.load_run(root)

    loaded = cs.load_run(root, expected_recipe_sha256=original["recipe_sha256"])
    report = cs.build_report(loaded)

    assert loaded == original
    assert fingerprints(root) == before
    assert report["recipe_sha256"] == original["recipe_sha256"]
    assert report["code_identity"] == "original-build"
    assert report["current_recipe_sha256"] == "f" * 64
    assert report["recipe_matches_current"] is False
    assert report["recorded_attempts"] == report["scheduled_attempts"] == 3
    assert sum(arm["failed"] for arm in report["arms"].values()) == 1
    assert report["reviewed_obligations"] == 0
    rendered = cs.render_report(report)
    assert original["recipe_sha256"] in rendered and "original-build" in rendered
    assert "recorded/current match: False" in rendered


@pytest.mark.parametrize("pin", ["", "abc", "A" * 64, "g" * 64])
def test_malformed_recipe_pin_refuses(retained, pin):
    root, _ = retained
    with pytest.raises(ValueError, match="64 lowercase hexadecimal"):
        cs.load_run(root, expected_recipe_sha256=pin)


def test_a_different_valid_pin_cannot_read_the_run(retained):
    root, _ = retained
    with pytest.raises(cs.RunNotReusableError, match="pinned recipe"):
        cs.load_run(root, expected_recipe_sha256="e" * 64)


@pytest.mark.parametrize("change", ["answer", "prompt", "marker", "case_set", "denominator"])
def test_pinned_review_keeps_existing_integrity_checks(retained, tmp_path, monkeypatch, change):
    source, original = retained
    root = tmp_path / "copy"
    shutil.copytree(source, root)
    if change in {"answer", "prompt"}:
        path = root / "attempts" / original["attempts"][0]["attempt_id"] / f"{change}.json"
        path.write_bytes(path.read_bytes() + b" ")
    elif change == "marker":
        (root / cs.COMPLETE_MARKER).unlink()
    elif change == "case_set":
        monkeypatch.setattr(cs, "case_set_sha256", lambda *_: "0" * 64)
    else:
        run = json.loads((root / "run.json").read_bytes())
        run["attempts"].pop()
        payload = json.dumps(run).encode()
        (root / "run.json").write_bytes(payload)
        marker = json.loads((root / cs.COMPLETE_MARKER).read_bytes())
        marker["run_sha256"] = hashlib.sha256(payload).hexdigest()
        (root / cs.COMPLETE_MARKER).write_text(json.dumps(marker), encoding="utf-8")

    with pytest.raises(cs.RunNotReusableError):
        cs.load_run(root, expected_recipe_sha256=original["recipe_sha256"])


@pytest.mark.parametrize("json_output", [False, True])
def test_cli_inspects_history_without_generation_or_writes(retained, tmp_path, monkeypatch, json_output):
    root, original = retained
    before = fingerprints(root)
    data = tmp_path / "unused-data"
    monkeypatch.setenv("DEEPR_DATA_DIR", str(data))
    monkeypatch.setattr(cs, "recipe_sha256", lambda: "f" * 64)

    def unexpected(*_args, **_kwargs):
        raise AssertionError("historical report attempted generation or routing")

    monkeypatch.setattr(cs, "run_diagnostic", unexpected)
    monkeypatch.setattr("deepr.evals.correction_survival_local.LocalAnswerer", unexpected)
    monkeypatch.setattr("deepr.experts.consult_routing.local_finding_router", unexpected)
    args = ["eval", "correction-survival-report", "--run-dir", str(root), "--recipe-sha256", original["recipe_sha256"]]
    result = CliRunner().invoke(cli, args + (["--json"] if json_output else []))

    assert result.exit_code == 0, result.output
    if json_output:
        report = json.loads(result.output)
        assert report["recipe_matches_current"] is False
        assert report["recorded_attempts"] == 3 and report["reviewed_obligations"] == 0
        assert "saved_to" not in report
    else:
        assert "recorded/current match: False" in result.output
        assert "original-build" in result.output
    assert not data.exists()
    assert fingerprints(root) == before


def test_cli_requires_a_recipe_pin_and_reports_a_mismatch_cleanly(retained):
    root, _ = retained
    args = ["eval", "correction-survival-report", "--run-dir", str(root)]
    missing = CliRunner().invoke(cli, args)
    assert missing.exit_code == 2
    assert "--recipe-sha256" in missing.output
    mismatch = CliRunner().invoke(cli, [*args, "--recipe-sha256", "e" * 64])
    assert mismatch.exit_code == 1
    assert "Error:" in mismatch.output and "pinned recipe" in mismatch.output


def test_old_report_does_not_invent_a_current_recipe_comparison(retained):
    _, run = retained
    report = cs.build_report(run)
    for field in ("code_identity", "current_recipe_sha256", "recipe_matches_current"):
        report.pop(field)
    assert "recorded/current match: None" in cs.render_report(report)
