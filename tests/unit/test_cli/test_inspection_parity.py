"""Installed inspection semantics without provider dispatch or incidental writes."""

import importlib
import json
from pathlib import Path

import pytest
from click.testing import CliRunner
from jsonschema import validate

from deepr.cli.main import cli


@pytest.mark.parametrize("flags", [[], ["--json"]])
def test_capacity_inspection_leaves_empty_working_directory_untouched(tmp_path, monkeypatch, flags):
    module = importlib.import_module("deepr.cli.commands.capacity")
    monkeypatch.setattr(module, "detect_capacity", lambda: [])
    monkeypatch.setattr(module, "probe_local_gpu_occupancy", lambda: None)
    monkeypatch.setattr(module, "_print_local_capacity", lambda value: None)
    monkeypatch.setattr(module, "_print_admissions_summary", lambda: None)
    monkeypatch.delenv("DEEPR_DATA_DIR", raising=False)
    monkeypatch.delenv("DEEPR_CAPACITY_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli, ["capacity", *flags])
    assert result.exit_code == 0, result.output
    assert list(tmp_path.iterdir()) == []
    if flags:
        assert json.loads(result.stdout) == []


@pytest.mark.parametrize(
    "provider,reason", [("openrouter", "tool spend"), ("xai", "tool spend"), ("openai", "reserved")]
)
def test_preview_explains_disabled_web_without_execution(provider, reason):
    result = CliRunner().invoke(cli, ["research", "A current question", "--provider", provider, "--preview", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["executed"] is False
    assert payload["tools"]["web_search"] is False
    assert reason in payload["tools"]["web_search_reason"]
    human = CliRunner().invoke(cli, ["research", "A current question", "--provider", provider, "--preview"])
    assert human.exit_code == 0, human.output
    assert " ".join(payload["tools"]["web_search_reason"].split()) in " ".join(human.output.split())
    assert "No live web sources" in human.output


def test_explicit_no_web_reason_is_distinguished():
    result = CliRunner().invoke(cli, ["research", "Question", "--preview", "--no-web", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["tools"]["web_search_reason"] == "Disabled by --no-web."


def test_doctor_json_and_human_counts_agree_without_generation():
    runner = CliRunner()
    machine = runner.invoke(cli, ["doctor", "--skip-connectivity", "--json"])
    payload = json.loads(machine.stdout)
    human = runner.invoke(cli, ["doctor", "--skip-connectivity"])
    assert human.exit_code == machine.exit_code
    validate(payload, json.loads((Path(__file__).parents[3] / "docs/schemas/doctor-v1.json").read_text()))
    assert payload["capacity"]["local_capacity_proof"] == "unverified"
    assert payload["capacity"]["generation_tested"] is False
    assert "Executable capacity not established" in human.stdout
    assert "Running checks" not in human.stdout
    counts = payload["counts"]
    normalized = " ".join(human.stdout.split())
    assert f"{counts['required_passed']}/{counts['required']} required checks passed" in normalized
    assert f"{counts['unverified']} unverified" in normalized
    if counts["errors"]:
        assert payload["error"]["category"] == "config"
        assert f"{counts['errors']} issue(s) need attention" in normalized


def test_expert_list_json_uses_the_same_stored_inventory_as_human():
    from deepr.experts.profile import ExpertProfile, ExpertStore

    ExpertStore().save(
        ExpertProfile(
            name="Inventory fixture",
            description="Stored description",
            vector_store_id="local",
            provider="local",
            model="fixture-model",
        )
    )
    runner = CliRunner()
    machine = runner.invoke(cli, ["expert", "list", "--json"])
    assert machine.exit_code == 0, machine.output
    payload = json.loads(machine.stdout)
    validate(payload, json.loads((Path(__file__).parents[3] / "docs/schemas/expert-inventory-v1.json").read_text()))
    assert payload["count"] == 1
    row = payload["experts"][0]
    human = runner.invoke(cli, ["expert", "list"])
    assert human.exit_code == 0, human.output
    assert row["name"] in human.stdout and row["description"] in human.stdout
    assert f"Claims: {row['claims']}" in human.stdout
    assert f"Documents: {row['documents']}" in human.stdout


def test_consult_missing_local_model_is_a_json_refusal(monkeypatch):
    from deepr.experts.profile import ExpertProfile, ExpertStore

    async def no_model():
        return None

    monkeypatch.setattr("deepr.backends.local.default_local_model_async", no_model)
    monkeypatch.setattr("deepr.backends.local.default_local_model", lambda: None)
    ExpertStore().save(ExpertProfile(name="Unformed fixture", vector_store_id="local", provider="local", model=""))
    result = CliRunner().invoke(
        cli, ["expert", "consult", "Question", "--expert", "Unformed fixture", "--local", "--json"]
    )
    assert result.exit_code == 2, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "CONSULT_CAPACITY_UNAVAILABLE"
    assert payload["error"]["category"] == "config"
    assert payload["error"]["retryable"] is False
    assert payload["error"]["hint"] == "deepr capacity --probe"


@pytest.mark.parametrize(
    "flags,code",
    [
        (["--provider", "openai"], "CONSULT_METERED_DISABLED"),
        (["--budget", "nan"], "CONSULT_INVALID_BUDGET"),
        (["--max-elapsed-seconds", "inf"], "CONSULT_INVALID_DEADLINE"),
    ],
)
def test_consult_validation_refusals_keep_json_parseable(flags, code):
    result = CliRunner().invoke(cli, ["expert", "consult", "Question", "--json", *flags])
    assert result.exit_code == 2, result.output
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == code
    assert payload["error"]["retryable"] is False


def test_capacity_partial_ledger_is_an_explicit_read_only_refusal(tmp_path, monkeypatch):
    module = importlib.import_module("deepr.cli.commands.capacity")
    monkeypatch.setattr(module, "detect_capacity", lambda: [])
    monkeypatch.setenv("DEEPR_CAPACITY_DATA_DIR", str(tmp_path))
    ledger = tmp_path / "quota_ledger.jsonl"
    original = b'{"backend_id": "codex"'
    ledger.write_bytes(original)
    result = CliRunner().invoke(cli, ["capacity", "--json"])
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "QUOTA_SNAPSHOT_UNAVAILABLE"
    assert payload["error"]["category"] == "storage"
    assert ledger.read_bytes() == original
    assert sorted(p.name for p in tmp_path.iterdir()) == ["quota_ledger.jsonl"]
