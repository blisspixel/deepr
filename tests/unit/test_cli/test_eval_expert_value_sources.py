"""Exercise the preparation command without a blueprint, provider, or writes."""

import json

import pytest
from click.testing import CliRunner

from deepr.cli.main import cli
from tests.unit.test_eval.test_expert_value_source_copy import make_copy
from tests.unit.test_eval.test_expert_value_sources import Bundle, _tree


def _arguments(bundle):
    return ["eval", "expert-value-sources", "--from-file", str(bundle.index_path), "--artifact-root", str(bundle.root)]


def test_source_preflight_cli_needs_no_attested_blueprint_and_writes_nothing(tmp_path):
    bundle = Bundle(tmp_path)
    before = _tree(tmp_path)
    result = CliRunner().invoke(cli, [*_arguments(bundle), "--json"])
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["source_world_count"] == 2
    assert report["execution_authorized"] is False
    assert _tree(tmp_path) == before


def test_source_preflight_cli_can_write_an_explicit_report_outside_the_evidence_root(tmp_path):
    bundle = Bundle(tmp_path / "evidence")
    output = tmp_path / "preflight.json"
    result = CliRunner().invoke(cli, [*_arguments(bundle), "--output", str(output)])
    assert result.exit_code == 0, result.output
    assert "Preparation only" in result.output
    assert json.loads(output.read_text())["evidence_writes"] == 0


@pytest.mark.parametrize("output_kind", ["input", "source", "new_evidence_file"])
def test_source_preflight_cannot_overwrite_or_add_evidence(tmp_path, output_kind):
    bundle = Bundle(tmp_path)
    output = {"input": bundle.index_path, "source": bundle.files[0], "new_evidence_file": tmp_path / "new.json"}[
        output_kind
    ]
    before = _tree(tmp_path)
    result = CliRunner().invoke(cli, [*_arguments(bundle), "--output", str(output)])
    assert result.exit_code != 0
    assert "must not overwrite" in result.output or "must be outside" in result.output
    assert _tree(tmp_path) == before


def test_source_preflight_refusal_returns_failure_and_leaves_output_absent(tmp_path):
    bundle = Bundle(tmp_path / "evidence")
    bundle.files[0].write_bytes(b"wrong source")
    output = tmp_path / "preflight.json"
    result = CliRunner().invoke(cli, [*_arguments(bundle), "--json", "--output", str(output)])
    assert result.exit_code != 0
    assert "Invalid source-world preparation" in result.output
    assert not output.exists()


@pytest.mark.parametrize("json_output", [True, False])
def test_copy_cli_reports_actual_inventory_without_writes(tmp_path, json_output):
    bundle = Bundle(tmp_path / "organizer")
    destination = make_copy(bundle, tmp_path / "worker")
    before = _tree(tmp_path)
    args = [*_arguments(bundle), "--world", "world-1", "--copy-root", str(destination)]
    result = CliRunner().invoke(cli, [*args, *(["--json"] if json_output else [])])
    assert result.exit_code == 0, result.output
    if json_output:
        report = json.loads(result.output)
        assert report["status"] == "source_copy_verified"
        assert report["verified_source_file_count"] == 1
    else:
        assert "Source copy verified: world-1, 1 independent source files" in result.output
        assert "isolation, blinding, and semantic quality remain unproven" in result.output
    assert _tree(tmp_path) == before


@pytest.mark.parametrize("missing", ["world", "copy"])
def test_copy_options_are_paired(tmp_path, missing):
    bundle = Bundle(tmp_path / "organizer")
    args = ["--copy-root", str(tmp_path)] if missing == "world" else ["--world", "world-1"]
    result = CliRunner().invoke(cli, [*_arguments(bundle), *args])
    assert result.exit_code == 2
    assert "must be supplied together" in result.output


@pytest.mark.parametrize("path", ["manifest.json", "sources/new.txt", "report.json"])
def test_report_cannot_change_or_pollute_verified_copy(tmp_path, path):
    bundle = Bundle(tmp_path / "organizer")
    destination = make_copy(bundle, tmp_path / "worker")
    before = _tree(tmp_path)
    result = CliRunner().invoke(
        cli,
        [
            *_arguments(bundle),
            "--world",
            "world-1",
            "--copy-root",
            str(destination),
            "--output",
            str(destination / path),
        ],
    )
    assert result.exit_code == 2
    assert "must be outside" in result.output
    assert _tree(tmp_path) == before


def test_copy_cli_refuses_extra_content_and_writes_no_receipt(tmp_path):
    bundle = Bundle(tmp_path / "organizer")
    destination = make_copy(bundle, tmp_path / "worker")
    (destination / "review-key.json").write_text("not worker input")
    output = tmp_path / "result.json"
    result = CliRunner().invoke(
        cli,
        [*_arguments(bundle), "--world", "world-1", "--copy-root", str(destination), "--output", str(output)],
    )
    assert result.exit_code == 1
    assert "unexpected entry" in result.output
    assert not output.exists()
