"""Exercise the preparation command without a blueprint, provider, or writes."""

import json

import pytest
from click.testing import CliRunner

from deepr.cli.main import cli
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
